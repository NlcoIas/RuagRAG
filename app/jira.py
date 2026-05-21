"""Jira REST API client — post comments, read issues, add labels.

Uses basic auth (email + API token) for Jira Cloud.
All functions are no-ops if Jira is not configured.
"""

import logging
from base64 import b64encode
from typing import Any

import httpx

from app.config import JIRA_API_TOKEN, JIRA_BASE_URL, JIRA_EMAIL, JIRA_ENABLED

logger = logging.getLogger(__name__)

JIRA_TIMEOUT = 15.0


def _auth_header() -> str:
    """Basic auth header value for Jira Cloud."""
    raw = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    return f"Basic {b64encode(raw.encode()).decode()}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def get_issue(issue_key: str) -> dict[str, Any] | None:
    """Fetch a Jira issue by key (e.g. FEEDBACK-1)."""
    if not JIRA_ENABLED:
        return None

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    async with httpx.AsyncClient(timeout=JIRA_TIMEOUT) as client:
        resp = await client.get(url, headers=_headers())
        if resp.status_code != 200:
            logger.error("Jira get_issue %s failed: %d %s", issue_key, resp.status_code, resp.text[:200])
            return None
        return resp.json()


async def add_comment(
    issue_key: str,
    body: str,
    internal: bool = True,
) -> bool:
    """Post a comment on a Jira issue.

    Args:
        issue_key: e.g. "FEEDBACK-1"
        body: Plain text comment body.
        internal: If True, post as internal comment (only agents see it).
                  Requires Jira Service Management. Falls back to public if not JSM.
    """
    if not JIRA_ENABLED:
        return False

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"

    # Atlassian Document Format (ADF) for the comment body
    adf_body: dict[str, Any] = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": body}],
            }
        ],
    }

    payload: dict[str, Any] = {"body": adf_body}

    # JSM internal comments use the "properties" field
    if internal:
        payload["properties"] = [
            {
                "key": "sd.public.comment",
                "value": {"internal": True},
            }
        ]

    async with httpx.AsyncClient(timeout=JIRA_TIMEOUT) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code in (200, 201):
            logger.info("Posted %s comment on %s", "internal" if internal else "public", issue_key)
            return True
        logger.error("Jira add_comment %s failed: %d %s", issue_key, resp.status_code, resp.text[:200])
        return False


async def add_label(issue_key: str, label: str) -> bool:
    """Add a label to a Jira issue."""
    if not JIRA_ENABLED:
        return False

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    payload = {"update": {"labels": [{"add": label}]}}

    async with httpx.AsyncClient(timeout=JIRA_TIMEOUT) as client:
        resp = await client.put(url, headers=_headers(), json=payload)
        if resp.status_code == 204:
            logger.info("Added label '%s' to %s", label, issue_key)
            return True
        logger.error("Jira add_label %s failed: %d %s", issue_key, resp.status_code, resp.text[:200])
        return False


def extract_issue_text(webhook_data: dict[str, Any]) -> tuple[str, str, str]:
    """Extract issue key, summary, and description from a Jira webhook payload.

    Returns: (issue_key, summary, description)
    """
    issue = webhook_data.get("issue", {})
    key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")

    # Description can be ADF (dict) or plain string
    desc_raw = fields.get("description")
    if isinstance(desc_raw, dict):
        # Extract text from ADF
        description = _adf_to_text(desc_raw)
    elif isinstance(desc_raw, str):
        description = desc_raw
    else:
        description = ""

    return key, summary, description


def _adf_to_text(adf: dict[str, Any]) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    texts: list[str] = []

    for block in adf.get("content", []):
        if block.get("type") == "paragraph":
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    texts.append(inline.get("text", ""))
            texts.append("\n")
        elif block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif "content" in block:
            texts.append(_adf_to_text(block))

    return "".join(texts).strip()


# --- Custom field IDs and option IDs ---
# Created via Jira REST API for the SUP project

FIELD_AI_CONFIDENCE = "customfield_10055"
FIELD_DEPARTMENT = "customfield_10056"
FIELD_TRIAGE_LEVEL = "customfield_10057"
FIELD_KB_SIMILARITY = "customfield_10058"
FIELD_TICKET_SIMILARITY = "customfield_10059"
FIELD_KB_BEST_MATCH = "customfield_10060"
FIELD_TICKET_BEST_MATCH = "customfield_10061"
FIELD_AI_SUGGESTED_RESPONSE = "customfield_10062"
FIELD_INTENT = "customfield_10128"
FIELD_ISSUE_CLASSIFICATION = "customfield_10129"
FIELD_LANGUAGE = "customfield_10130"
FIELD_SEVERITY = "customfield_10131"

# Select field option IDs (value → Jira option ID)
CONFIDENCE_OPTIONS = {"High": "10032", "Medium": "10033", "Low": "10034"}
DEPARTMENT_OPTIONS = {
    "IT": "10035", "HR": "10036", "Facilities": "10037",
    "Finance": "10038", "Legal": "10039", "General": "10040",
}
TRIAGE_OPTIONS = {
    "L1 - Self-Service": "10041", "L2 - Agent": "10042", "L3 - Expert": "10043",
}

INTENT_OPTIONS = {
    "feature_request": "10076", "bug_report": "10077", "how_to": "10078",
    "access_request": "10079", "complaint": "10080", "general_inquiry": "10081",
}
ISSUE_CLASSIFICATION_OPTIONS = {
    "context_handling": "10082", "troubleshooting": "10083", "configuration": "10084",
    "account_management": "10085", "information": "10086", "other": "10087",
}
SEVERITY_OPTIONS = {"S1": "10088", "S2": "10089", "S3": "10090", "S4": "10091"}

# Jira priority name → ID mapping (built-in)
PRIORITY_MAP = {"Highest": "1", "High": "2", "Medium": "3", "Low": "4", "Lowest": "5"}


async def set_triage_fields(
    issue_key: str,
    department: str,
    urgency: str,
    confidence: str,
    triage_level: str,
    kb_score: float,
    kb_match: str,
    ticket_score: float,
    ticket_match: str,
    suggested_response: str,
    intent: str = "",
    issue_type: str = "",
    language: str = "",
    severity: str = "",
) -> bool:
    """Set all AI triage fields on a Jira issue."""
    if not JIRA_ENABLED:
        return False

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"

    fields: dict[str, Any] = {}

    # Priority (built-in field)
    if urgency in PRIORITY_MAP:
        fields["priority"] = {"id": PRIORITY_MAP[urgency]}

    # Select fields (need option ID format)
    if confidence in CONFIDENCE_OPTIONS:
        fields[FIELD_AI_CONFIDENCE] = {"id": CONFIDENCE_OPTIONS[confidence]}
    if department in DEPARTMENT_OPTIONS:
        fields[FIELD_DEPARTMENT] = {"id": DEPARTMENT_OPTIONS[department]}
    if triage_level in TRIAGE_OPTIONS:
        fields[FIELD_TRIAGE_LEVEL] = {"id": TRIAGE_OPTIONS[triage_level]}
    if intent in INTENT_OPTIONS:
        fields[FIELD_INTENT] = {"id": INTENT_OPTIONS[intent]}
    if issue_type in ISSUE_CLASSIFICATION_OPTIONS:
        fields[FIELD_ISSUE_CLASSIFICATION] = {"id": ISSUE_CLASSIFICATION_OPTIONS[issue_type]}
    if severity in SEVERITY_OPTIONS:
        fields[FIELD_SEVERITY] = {"id": SEVERITY_OPTIONS[severity]}

    # Number fields
    fields[FIELD_KB_SIMILARITY] = kb_score
    fields[FIELD_TICKET_SIMILARITY] = ticket_score

    # Text fields
    fields[FIELD_KB_BEST_MATCH] = kb_match[:250]
    fields[FIELD_TICKET_BEST_MATCH] = ticket_match[:250]
    if language:
        fields[FIELD_LANGUAGE] = language
    # Textarea fields require Atlassian Document Format
    fields[FIELD_AI_SUGGESTED_RESPONSE] = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": suggested_response[:5000]}],
            }
        ],
    }

    payload = {"fields": fields}

    async with httpx.AsyncClient(timeout=JIRA_TIMEOUT) as client:
        resp = await client.put(url, headers=_headers(), json=payload)
        if resp.status_code == 204:
            logger.info("Set triage fields on %s: dept=%s conf=%s level=%s", issue_key, department, confidence, triage_level)
            return True
        logger.error("Jira set_triage_fields %s failed: %d %s", issue_key, resp.status_code, resp.text[:300])
        return False


def is_resolution_event(webhook_data: dict[str, Any]) -> bool:
    """Check if the webhook event is a ticket being resolved.

    Detects both:
    - Standard Jira: changelog field="resolution" with a "to" value
    - JSM workflows: changelog field="status" transitioning to a resolved state
    """
    event = webhook_data.get("webhookEvent", "")
    changelog = webhook_data.get("changelog", {})

    if event != "jira:issue_updated":
        return False

    resolved_statuses = {"resolved", "done", "closed", "erledigt"}

    for item in changelog.get("items", []):
        # Standard resolution field
        if item.get("field") == "resolution" and item.get("to"):
            return True
        # JSM status transition to a resolved state
        if item.get("field") == "status":
            to_str = (item.get("toString") or "").lower()
            if to_str in resolved_statuses:
                return True

    return False
