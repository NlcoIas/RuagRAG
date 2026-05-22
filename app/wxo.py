"""watsonx Orchestrate service — IAM auth and async chat.

Flow: get IAM token -> submit run to wxO -> poll until completed -> parse response.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import (
    IBM_CLOUD_API_KEY,
    WXO_AGENT_ID,
    WXO_ENV_ID,
    WXO_INSTANCE_ID,
    WXO_URL,
)

logger = logging.getLogger(__name__)

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
WXO_TIMEOUT = 30.0

# IAM token cache (refreshes every 55 min, actual TTL is 60 min)
_cached_token: str | None = None
_token_expiry: float = 0.0


async def _get_iam_token() -> str:
    """Get or refresh the IBM Cloud IAM bearer token."""
    global _cached_token, _token_expiry

    now = time.time()
    if _cached_token and now < _token_expiry:
        return _cached_token

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            IAM_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": IBM_CLOUD_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _cached_token = data["access_token"]
    server_exp = data.get("expiration", 0)
    _token_expiry = float(server_exp) - 300 if server_exp else now + 55 * 60
    logger.info("IAM token refreshed")
    return _cached_token


def _clear_token_cache() -> None:
    """Force token refresh on next call."""
    global _cached_token, _token_expiry
    _cached_token = None
    _token_expiry = 0.0


def _parse_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract reply + sources from wxO's completed run response.

    wxO shape: result.data.message.content[].text + citations[].
    """
    reply = ""
    thread_id = data.get("thread_id", "")
    sources: list[dict[str, Any]] = []

    result = data.get("result", {})
    msg_data = result.get("data", {}) if isinstance(result, dict) else {}
    message = msg_data.get("message", {}) if isinstance(msg_data, dict) else {}
    content_list = message.get("content", []) if isinstance(message, dict) else []

    if isinstance(content_list, list):
        for block in content_list:
            if isinstance(block, dict) and "text" in block:
                reply = block["text"]
                for cit in block.get("citations", []):
                    if isinstance(cit, dict):
                        sources.append({
                            "title": cit.get("title", ""),
                            "body": cit.get("body", ""),
                        })
                break

    return {"reply": reply, "thread_id": thread_id, "sources": sources}


async def check_connection() -> str:
    """Verify wxO is reachable by getting an IAM token."""
    try:
        await _get_iam_token()
        return "connected"
    except Exception as exc:
        return f"error: {exc}"


async def chat(
    message: str,
    thread_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Send a message to the wxO agent and return the response.

    Args:
        message: The user's message.
        thread_id: Pass to continue an existing conversation. None = new conversation.
        agent_id: Override the default agent. None = use WXO_AGENT_ID from config.

    Returns: {"reply": str, "thread_id": str, "sources": list}
    Never raises — returns error messages in the reply field.
    """
    # 1. Get IAM token
    try:
        token = await _get_iam_token()
    except Exception as exc:
        logger.error("IAM token failed: %s", exc)
        return {"reply": f"Authentication error: {exc}", "thread_id": "", "sources": []}

    # 2. Submit run
    base_url = f"{WXO_URL.rstrip('/')}/instances/{WXO_INSTANCE_ID}"
    run_url = f"{base_url}/v1/orchestrate/runs"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "message": {"role": "user", "content": message},
        "agent_id": agent_id or WXO_AGENT_ID,
    }
    if WXO_ENV_ID:
        body["environment_id"] = WXO_ENV_ID
    if thread_id:
        body["thread_id"] = thread_id

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=WXO_TIMEOUT) as client:
                resp = await client.post(run_url, headers=headers, json=body)

                # Retry once on 401 (token expired)
                if resp.status_code == 401 and attempt == 0:
                    logger.warning("wxO 401, refreshing token")
                    _clear_token_cache()
                    token = await _get_iam_token()
                    headers["Authorization"] = f"Bearer {token}"
                    continue

                if resp.status_code >= 400:
                    logger.error("wxO error %d: %s", resp.status_code, resp.text[:300])
                    return {
                        "reply": f"wxO error (HTTP {resp.status_code}). Try again later.",
                        "thread_id": thread_id or "",
                        "sources": [],
                    }

                run_data = resp.json()
                run_id = run_data.get("run_id", "")
                wxo_thread = run_data.get("thread_id", thread_id or "")

                # No run_id = synchronous response
                if not run_id:
                    result = _parse_response(run_data)
                    result["thread_id"] = result["thread_id"] or wxo_thread
                    return result

                # 3. Poll for completion
                poll_url = f"{base_url}/v1/orchestrate/runs/{run_id}"
                for _ in range(25):
                    await asyncio.sleep(1)
                    poll = await client.get(
                        poll_url, headers=headers, params={"thread_id": wxo_thread}
                    )
                    if poll.status_code != 200:
                        continue
                    poll_data = poll.json()
                    status = poll_data.get("status", "")

                    if status == "completed":
                        result = _parse_response(poll_data)
                        result["thread_id"] = result["thread_id"] or wxo_thread
                        if not result["reply"]:
                            result["reply"] = "Agent returned an empty response."
                        return result

                    if status in ("failed", "cancelled"):
                        err = poll_data.get("last_error", {})
                        return {
                            "reply": f"Agent failed: {err.get('message', 'Unknown')}",
                            "thread_id": wxo_thread,
                            "sources": [],
                        }

                return {
                    "reply": "Agent took too long. Please try again.",
                    "thread_id": wxo_thread,
                    "sources": [],
                }

        except httpx.TimeoutException:
            return {
                "reply": "Request timed out. Please try again.",
                "thread_id": thread_id or "",
                "sources": [],
            }
        except Exception as exc:
            logger.error("wxO request failed: %s", exc)
            return {
                "reply": f"Unexpected error: {exc}",
                "thread_id": thread_id or "",
                "sources": [],
            }

    return {"reply": "Auth failed after retry.", "thread_id": "", "sources": []}
