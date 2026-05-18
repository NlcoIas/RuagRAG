"""RuagRAG — FastAPI backend for RUAG Feedback Management.

FastAPI is the hub:
- Frontend talks to FastAPI (chat, tickets, dashboard)
- FastAPI proxies chat to wxO (user messages → wxO reasoning → response)
- wxO calls FastAPI back as tools (search KB, search tickets)
- Jira webhook → FastAPI → Granite → Jira comment
"""

import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request

from app import astra, jira, wxo
from app.config import JIRA_ENABLED
from app.triage import triage_ticket
from app.schemas import (
    ChatRequest,
    ChatResponse,
    CountResponse,
    DeleteResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    JiraWebhookResponse,
    RefineRequest,
    RefineResponse,
    SearchRequest,
    SearchResponse,
    UpdateRequest,
    UpdateResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RuagRAG API",
    description="RUAG Feedback Management — IBM watsonx Agentic AI",
    version="0.4.0",
)


# --- Health ---


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Check Astra DB and wxO connections."""
    astra_status = astra.check_connection()
    wxo_status = await wxo.check_connection()

    if astra_status == "connected" and wxo_status == "connected":
        status = "ok"
    elif astra_status == "connected" or wxo_status == "connected":
        status = "degraded"
    else:
        status = "error"

    return HealthResponse(
        status=status,
        astra_db=astra_status,
        wxo=wxo_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# --- Chat (frontend → FastAPI → wxO) ---


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Forward a user message to wxO and return the agent's response.

    This is the frontend's entry point to wxO. FastAPI proxies the message,
    and later will also create tickets, log conversations, and update the audit trail.
    """
    result = await wxo.chat(
        message=body.message,
        thread_id=body.thread_id,
        agent_id=body.agent_id,
    )
    return ChatResponse(**result)


# --- Knowledge Base (wxO calls these as tools) ---


@app.post(
    "/api/rag/knowledge/search",
    response_model=SearchResponse,
    operation_id="search_knowledge_base",
    description="Search the company knowledge base for relevant documents. Returns ranked results by semantic similarity.",
)
async def kb_search(body: SearchRequest):
    results = await astra.search(
        collection="knowledge_base", query=body.query, limit=body.limit
    )
    return SearchResponse(results=results, count=len(results))


@app.post(
    "/api/rag/knowledge/ingest",
    response_model=IngestResponse,
    operation_id="ingest_knowledge_document",
    description="Add or update a document in the knowledge base.",
)
async def kb_ingest(body: IngestRequest):
    success = await astra.ingest(
        collection="knowledge_base",
        doc_id=body.doc_id,
        text=body.text,
        metadata=body.metadata,
    )
    return IngestResponse(success=success, doc_id=body.doc_id)


@app.get(
    "/api/rag/knowledge/count",
    response_model=CountResponse,
    operation_id="count_knowledge_documents",
    description="Count documents in the knowledge base.",
)
async def kb_count():
    c = await astra.count("knowledge_base")
    return CountResponse(collection="knowledge_base", count=c)


@app.delete(
    "/api/rag/knowledge/clear",
    response_model=DeleteResponse,
    operation_id="clear_knowledge_base",
    description="Delete all documents from the knowledge base.",
)
async def kb_clear():
    deleted = await astra.delete_all("knowledge_base")
    return DeleteResponse(success=True, collection="knowledge_base", deleted_count=deleted)


@app.put(
    "/api/rag/knowledge/{doc_id}",
    response_model=UpdateResponse,
    operation_id="update_knowledge_document",
    description="Update a document's text and/or metadata in the knowledge base.",
)
async def kb_update(doc_id: str, body: UpdateRequest):
    if body.text is None and body.metadata is None:
        raise HTTPException(status_code=422, detail="Provide text and/or metadata to update")
    success = await astra.update(
        collection="knowledge_base",
        doc_id=doc_id,
        text=body.text,
        metadata=body.metadata,
    )
    return UpdateResponse(success=success, doc_id=doc_id)


@app.delete(
    "/api/rag/knowledge/{doc_id}",
    response_model=DeleteResponse,
    operation_id="delete_knowledge_document",
    description="Delete a specific document from the knowledge base.",
)
async def kb_delete(doc_id: str):
    success = await astra.delete_one("knowledge_base", doc_id)
    return DeleteResponse(success=success, doc_id=doc_id)


# --- Resolved Tickets (wxO calls these as tools) ---


@app.post(
    "/api/rag/tickets/search",
    response_model=SearchResponse,
    operation_id="search_resolved_tickets",
    description="Search resolved support tickets for similar past cases and their solutions.",
)
async def tickets_search(body: SearchRequest):
    results = await astra.search(
        collection="resolved_tickets", query=body.query, limit=body.limit
    )
    return SearchResponse(results=results, count=len(results))


@app.post(
    "/api/rag/tickets/ingest",
    response_model=IngestResponse,
    operation_id="ingest_resolved_ticket",
    description="Add or update a resolved ticket.",
)
async def tickets_ingest(body: IngestRequest):
    success = await astra.ingest(
        collection="resolved_tickets",
        doc_id=body.doc_id,
        text=body.text,
        metadata=body.metadata,
    )
    return IngestResponse(success=success, doc_id=body.doc_id)


@app.get(
    "/api/rag/tickets/count",
    response_model=CountResponse,
    operation_id="count_resolved_tickets",
    description="Count documents in the resolved tickets collection.",
)
async def tickets_count():
    c = await astra.count("resolved_tickets")
    return CountResponse(collection="resolved_tickets", count=c)


@app.put(
    "/api/rag/tickets/{doc_id}",
    response_model=UpdateResponse,
    operation_id="update_resolved_ticket",
    description="Update a resolved ticket's text and/or metadata.",
)
async def tickets_update(doc_id: str, body: UpdateRequest):
    if body.text is None and body.metadata is None:
        raise HTTPException(status_code=422, detail="Provide text and/or metadata to update")
    success = await astra.update(
        collection="resolved_tickets",
        doc_id=doc_id,
        text=body.text,
        metadata=body.metadata,
    )
    return UpdateResponse(success=success, doc_id=doc_id)


@app.delete(
    "/api/rag/tickets/clear",
    response_model=DeleteResponse,
    operation_id="clear_resolved_tickets",
    description="Delete all documents from the resolved tickets collection.",
)
async def tickets_clear():
    deleted = await astra.delete_all("resolved_tickets")
    return DeleteResponse(success=True, collection="resolved_tickets", deleted_count=deleted)


@app.delete(
    "/api/rag/tickets/{doc_id}",
    response_model=DeleteResponse,
    operation_id="delete_resolved_ticket",
    description="Delete a specific resolved ticket.",
)
async def tickets_delete(doc_id: str):
    success = await astra.delete_one("resolved_tickets", doc_id)
    return DeleteResponse(success=success, doc_id=doc_id)


# --- Jira Webhook ---


async def _handle_new_ticket(issue_key: str, summary: str, description: str) -> None:
    """Background task: triage ticket via dual RAG + Granite, set all fields."""
    logger.info("Triaging ticket %s: %s", issue_key, summary)

    # Run the full triage pipeline (dual search + Granite classification)
    result = await triage_ticket(summary, description)

    # Set all custom fields on the Jira ticket
    await jira.set_triage_fields(
        issue_key=issue_key,
        department=result.department,
        urgency=result.urgency,
        confidence=result.confidence,
        triage_level=result.triage_level,
        kb_score=result.kb_score,
        kb_match=result.kb_match,
        ticket_score=result.ticket_score,
        ticket_match=result.ticket_match,
        suggested_response=result.suggested_response,
    )

    # Also post the suggested response as an internal comment for quick viewing
    comment = (
        f"🤖 AI Triage Complete\n\n"
        f"Department: {result.department}\n"
        f"Confidence: {result.confidence} | Level: {result.triage_level}\n"
        f"KB Score: {result.kb_score:.2f} | Ticket Score: {result.ticket_score:.2f}\n\n"
        f"Suggested Response:\n{result.suggested_response}"
    )

    await jira.add_comment(issue_key, comment, internal=True)
    await jira.add_label(issue_key, "ai-triaged")


async def _handle_resolution(issue_key: str, summary: str, description: str) -> None:
    """Background task: ingest resolved ticket Q+A into Astra for future RAG."""
    question = f"{summary}\n\n{description}".strip()

    # Fetch the issue to get resolution comments
    issue_data = await jira.get_issue(issue_key)
    resolution_comment = ""
    if issue_data:
        comments = issue_data.get("fields", {}).get("comment", {}).get("comments", [])
        # Use the last non-AI comment as the resolution
        for c in reversed(comments):
            body = c.get("body", {})
            text = jira._adf_to_text(body) if isinstance(body, dict) else str(body)
            if not text.startswith("🤖 AI Suggestion:"):
                resolution_comment = text
                break

    doc_text = f"Question: {question}\n\nResolution: {resolution_comment}" if resolution_comment else question

    await astra.ingest(
        collection="resolved_tickets",
        doc_id=f"jira-{issue_key}",
        text=doc_text,
        metadata={"source": "jira", "issue_key": issue_key, "summary": summary},
    )
    logger.info("Ingested resolved ticket %s into resolved_tickets", issue_key)


@app.post("/api/jira/webhook", response_model=JiraWebhookResponse)
async def jira_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Jira webhook events.

    Handles two event types:
    - Issue created → send to Granite agent, post AI response as internal comment
    - Issue resolved → ingest Q+A into resolved_tickets for future RAG
    """
    if not JIRA_ENABLED:
        raise HTTPException(status_code=503, detail="Jira integration not configured")

    body = await request.body()
    if not body:
        return JiraWebhookResponse(
            issue_key="", action="ignored", success=False, detail="Empty body"
        )

    import json as _json
    data = _json.loads(body)
    event = data.get("webhookEvent", "")
    issue_key, summary, description = jira.extract_issue_text(data)

    logger.info("Webhook: event=%s key=%s", event, issue_key)

    if not issue_key:
        return JiraWebhookResponse(
            issue_key="", action="ignored", success=False, detail="No issue key found"
        )

    # Ticket resolved → ingest for future RAG
    if jira.is_resolution_event(data):
        background_tasks.add_task(_handle_resolution, issue_key, summary, description)
        return JiraWebhookResponse(
            issue_key=issue_key, action="ingested", success=True,
            detail="Resolution will be ingested into knowledge base",
        )

    # New ticket created → send to Granite
    if event == "jira:issue_created":
        background_tasks.add_task(_handle_new_ticket, issue_key, summary, description)
        return JiraWebhookResponse(
            issue_key=issue_key, action="ai_response", success=True,
            detail="AI response will be posted as internal comment",
        )

    return JiraWebhookResponse(
        issue_key=issue_key, action="ignored", success=True,
        detail=f"Event '{event}' not handled",
    )


# --- Refine (Forge → FastAPI → wxO rewrite) ---


async def _verify_forge_key(request: Request) -> None:
    """Validate the Forge API key if one is configured."""
    from app import config as _cfg  # read at call-time so tests can patch app.config.FORGE_API_KEY

    if not _cfg.FORGE_API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {_cfg.FORGE_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.post("/api/refine", response_model=RefineResponse, dependencies=[Depends(_verify_forge_key)])
async def refine(body: RefineRequest):
    """Rewrite an AI-generated response based on agent feedback.

    Called by the Forge issue panel. Sends a simple rewrite prompt to wxO
    (no RAG, no tool-calling — just text transformation).
    """
    prompt = (
        f"Rewrite the following customer support response.\n"
        f"Apply this feedback: {body.feedback}\n\n"
        f"CURRENT RESPONSE:\n{body.current_text}\n\n"
        f"Return ONLY the rewritten response text. No explanations, no formatting, no preamble."
    )

    if body.issue_key:
        logger.info("Refine request for %s: %s", body.issue_key, body.feedback[:100])

    result = await wxo.chat(message=prompt)
    reply = result.get("reply", "").strip()

    if not reply:
        return RefineResponse(refined_text=body.current_text, success=False)

    return RefineResponse(refined_text=reply, success=True)
