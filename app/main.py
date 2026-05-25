"""RuagRAG — FastAPI backend for RUAG Feedback Management.

FastAPI is the hub:
- Frontend talks to FastAPI (chat, tickets, dashboard)
- FastAPI proxies chat to wxO (user messages → wxO reasoning → response)
- wxO calls FastAPI back as tools (search KB, search tickets)
- Jira webhook → FastAPI → Granite → Jira comment
"""

import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
        intent=result.intent,
        issue_type=result.issue_type,
        language=result.language,
        severity=result.severity,
        information_complete=result.information_complete,
    )

    await jira.add_label(issue_key, "ai-triaged")

    # L3 escalation — flag ticket for expert attention
    if result.triage_level == "L3 - Expert":
        await jira.add_label(issue_key, "escalated")
        # Ensure priority is at least High for L3
        if result.urgency not in ("Highest", "High"):
            await jira.set_priority(issue_key, "High")
        # Post internal escalation note so agents see it immediately
        esc_note = (
            f"ESCALATION: This ticket has been triaged as L3 - Expert.\n\n"
            f"Reason: AI confidence is {result.confidence} "
            f"(score: {result.confidence_score:.2f}). "
            f"Department: {result.department}. Severity: {result.severity}.\n"
            f"KB match score: {result.kb_score:.2f} | "
            f"Ticket match score: {result.ticket_score:.2f}\n\n"
            f"This ticket requires specialist review."
        )
        await jira.add_comment(issue_key, esc_note, internal=True)
        logger.info("Escalated %s to L3 - Expert (conf=%s)", issue_key, result.confidence)

    # If information is incomplete, auto-reply to customer asking for more details
    if not result.information_complete:
        info_request_messages = {
            "de": (
                "Vielen Dank fuer Ihre Anfrage. Um Ihnen besser helfen zu koennen, "
                "benoetigen wir noch folgende Informationen:\n\n"
                "- Welches Produkt oder System ist betroffen?\n"
                "- Welche Schritte haben Sie vor dem Problem durchgefuehrt?\n"
                "- Gibt es eine Fehlermeldung?\n\n"
                "Diese Angaben helfen uns, Ihr Anliegen schneller zu loesen."
            ),
            "fr": (
                "Merci pour votre demande. Pour vous aider plus efficacement, "
                "pourriez-vous nous fournir les informations suivantes:\n\n"
                "- Quel produit ou systeme est concerne?\n"
                "- Quelles etapes avez-vous effectuees avant le probleme?\n"
                "- Y a-t-il un message d'erreur?\n\n"
                "Ces informations nous aideront a resoudre votre probleme plus rapidement."
            ),
            "it": (
                "Grazie per la sua richiesta. Per aiutarla in modo piu efficace, "
                "potrebbe fornirci le seguenti informazioni:\n\n"
                "- Quale prodotto o sistema e interessato?\n"
                "- Quali passaggi ha eseguito prima del problema?\n"
                "- C'e un messaggio di errore?\n\n"
                "Queste informazioni ci aiuteranno a risolvere il problema piu velocemente."
            ),
        }
        lang = result.language[:2] if result.language else "en"
        ask_msg = info_request_messages.get(lang, (
            "Thank you for your request. To help you more effectively, "
            "could you please provide the following details:\n\n"
            "- What product or system is affected?\n"
            "- What steps did you take before the issue occurred?\n"
            "- Are there any error messages?\n\n"
            "This will help us resolve your issue faster."
        ))

        await jira.add_comment(issue_key, ask_msg, internal=False)
        logger.info("Auto-replied to %s requesting more information (lang=%s)", issue_key, lang)


async def _handle_resolution(issue_key: str, summary: str, description: str) -> None:
    """Background task: ingest resolved ticket Q+A into Astra with full metadata."""
    question = f"{summary}\n\n{description}".strip()

    # Fetch the full issue to get all fields + comments
    issue_data = await jira.get_issue(issue_key)
    if not issue_data:
        logger.error("Could not fetch issue %s for resolution ingestion", issue_key)
        return

    fields = issue_data.get("fields", {})

    # Extract conversation turns from comments
    comments = fields.get("comment", {}).get("comments", [])
    user_turns = [question]
    assistant_turns = []
    resolution_comment = ""

    for c in comments:
        body = c.get("body", {})
        text = jira._adf_to_text(body) if isinstance(body, dict) else str(body)
        if not text:
            continue

        # Check if internal (AI/agent) or external (customer)
        is_internal = False
        for prop in c.get("properties", []):
            if prop.get("key") == "sd.public.comment":
                is_internal = prop.get("value", {}).get("internal", False)

        if text.startswith("🤖"):
            assistant_turns.append(text)
        elif is_internal:
            assistant_turns.append(text)
        else:
            user_turns.append(text)

    # Last non-AI comment is the resolution
    for c in reversed(comments):
        body = c.get("body", {})
        text = jira._adf_to_text(body) if isinstance(body, dict) else str(body)
        if text and not text.startswith("🤖"):
            resolution_comment = text
            break

    # Extract triage fields (set during initial triage)
    confidence_field = fields.get("customfield_10055")
    department_field = fields.get("customfield_10056")
    triage_field = fields.get("customfield_10057")
    kb_score = fields.get("customfield_10058") or 0
    ticket_score = fields.get("customfield_10059") or 0
    kb_match = fields.get("customfield_10060") or ""
    ticket_match = fields.get("customfield_10061") or ""

    confidence = confidence_field.get("value", "") if isinstance(confidence_field, dict) else ""
    department = department_field.get("value", "") if isinstance(department_field, dict) else ""
    triage_level = triage_field.get("value", "") if isinstance(triage_field, dict) else ""

    # Extract new classification fields
    intent_field = fields.get("customfield_10128")
    issue_class_field = fields.get("customfield_10129")
    severity_field = fields.get("customfield_10131")
    language = fields.get("customfield_10130") or ""
    intent = intent_field.get("value", "") if isinstance(intent_field, dict) else ""
    issue_classification = issue_class_field.get("value", "") if isinstance(issue_class_field, dict) else ""

    # Severity from custom field or mapped from priority
    priority = fields.get("priority", {}).get("name", "Medium")
    severity_map = {"Highest": "S1", "High": "S2", "Medium": "S3", "Low": "S4", "Lowest": "S4"}
    severity_from_field = severity_field.get("value", "") if isinstance(severity_field, dict) else ""
    severity = severity_from_field or severity_map.get(priority, "S3")
    urgency = priority

    # Extract CSAT feedback if available (from built-in satisfaction or our custom field)
    satisfaction = fields.get("customfield_10041")
    customer_rating_text = fields.get("customfield_10197") or ""
    rating = None  # Default None = no rating yet
    if isinstance(satisfaction, dict) and satisfaction.get("rating"):
        rating = satisfaction.get("rating")
    elif customer_rating_text and "(" in customer_rating_text:
        # Parse from "★★★★☆ (4/5)" format
        try:
            rating = int(customer_rating_text.split("(")[1].split("/")[0])
        except (IndexError, ValueError):
            pass

    # Extract reporter info
    reporter = fields.get("reporter", {})
    reporter_name = reporter.get("displayName", "")
    reporter_id = reporter.get("accountId", "")

    # Build combined text for vectorization (Q+A format)
    doc_text = f"Question: {question}\n\nResolution: {resolution_comment}" if resolution_comment else question

    # Build rich metadata matching the Ticket DB schema
    metadata = {
        "source": "jira",
        "issue_key": issue_key,
        "summary": summary,
        "type": "resolved_tickets",
        "department": department,
        "confidence": confidence,
        "triage_level": triage_level,
        "urgency": urgency,
        "severity": severity,
        "kb_score": float(kb_score),
        "ticket_score": float(ticket_score),
        "kb_match": kb_match[:250],
        "ticket_match": ticket_match[:250],
        "intent": intent,
        "issue_classification": issue_classification,
        "language": language,
        "persona_role": reporter_name,
        "persona_id": reporter_id,
        "user_turns": len(user_turns),
        "assistant_turns": len(assistant_turns),
        "rating": rating,
    }

    await astra.ingest(
        collection="resolved_tickets",
        doc_id=f"jira-{issue_key}",
        text=doc_text,
        metadata=metadata,
    )

    # Build conversation string for redundancy checker
    conversation_lines = []
    for turn in user_turns:
        conversation_lines.append(f"User: {turn}")
    for turn in assistant_turns:
        conversation_lines.append(f"Assistant: {turn}")
    conversation_str = "\n".join(conversation_lines)
    vectorize_text = " ".join(user_turns)

    # Call redundancy checker before inserting into ticket_db
    # The redundancy service handles the insert if decision=POST
    redundancy_url = "https://ruag-ticket-redundancy.27cltkbcyac0.eu-de.codeengine.appdomain.cloud"
    redundancy_payload = {
        "title": issue_key,
        "intent": intent or None,
        "issue_type": issue_classification or None,
        "severity": severity or None,
        "urgency": urgency.lower() or None,
        "language": language or None,
        "persona_role": reporter_name or None,
        "persona_access_tier": None,
        "gold_doc_ids": kb_match if kb_match != "No match" else None,
        "vectorize_text": vectorize_text,
        "conversation": conversation_str,
    }

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{redundancy_url}/redundancy-check",
                json=redundancy_payload,
            )
            if resp.status_code == 200:
                result = resp.json()
                decision = result.get("decision", "POST")
                reason = result.get("reason", "")
                matched_id = result.get("matched_ticket_id")
                llm_checked = result.get("llm_checked", False)
                logger.info(
                    "Redundancy check %s: decision=%s llm_checked=%s matched=%s reason=%s",
                    issue_key, decision, llm_checked, matched_id, reason,
                )
            else:
                logger.warning(
                    "Redundancy check failed for %s (HTTP %d), inserting anyway",
                    issue_key, resp.status_code,
                )
    except Exception as exc:
        logger.warning("Redundancy check error for %s: %s, skipping", issue_key, exc)

    logger.info("Ingested resolved ticket %s into resolved_tickets (ticket_db via redundancy checker)", issue_key)


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
        # Empty body but triggered by user — likely a comment event
        # Check if triggeredByUser is in query params
        triggered_by = request.query_params.get("triggeredByUser", "")
        if not triggered_by:
            return JiraWebhookResponse(
                issue_key="", action="ignored", success=False, detail="Empty body"
            )
        # Can't determine which issue — ignore for now
        logger.info("Webhook: empty body with triggeredByUser=%s", triggered_by)
        return JiraWebhookResponse(
            issue_key="", action="ignored", success=False, detail="Empty body with user trigger"
        )

    import json as _json
    try:
        data = _json.loads(body)
    except _json.JSONDecodeError as exc:
        logger.error("Webhook JSON parse error: %s body[:200]=%s", exc, body[:200])
        return JiraWebhookResponse(
            issue_key="", action="ignored", success=False, detail=f"Invalid JSON: {exc}"
        )
    event = data.get("webhookEvent", "")
    issue_key, summary, description = jira.extract_issue_text(data)

    # Handle comment_created from Jira Automation (minimal payload with just issue key)
    if event == "comment_created" and not issue_key:
        issue_key = data.get("issue", {}).get("key", "")

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

    # Customer added a comment → re-triage with full conversation context
    # Handles both: Jira webhook (jira:issue_updated) and Automation (comment_created)
    if event == "comment_created" or (event == "jira:issue_updated" and _is_customer_comment(data)):
        background_tasks.add_task(_handle_customer_update, issue_key)
        return JiraWebhookResponse(
            issue_key=issue_key, action="re_triage", success=True,
            detail="Customer comment detected, re-triaging with full context",
        )

    return JiraWebhookResponse(
        issue_key=issue_key, action="ignored", success=True,
        detail=f"Event '{event}' not handled",
    )


def _is_customer_comment(webhook_data: dict) -> bool:
    """Check if the webhook event is a customer adding a public comment."""
    changelog = webhook_data.get("changelog", {})
    comment = webhook_data.get("comment")

    # Direct comment in webhook payload (public, not internal)
    if comment:
        for prop in comment.get("properties", []):
            if prop.get("key") == "sd.public.comment":
                if not prop.get("value", {}).get("internal", True):
                    return True
        # If no properties, check if it's from a non-agent user
        if not comment.get("properties"):
            return True

    # Changelog indicates a comment was added
    for item in changelog.get("items", []):
        if item.get("field") == "Comment":
            return True

    return False


async def _handle_customer_update(issue_key: str) -> None:
    """Background task: re-triage ticket after customer provides more info."""
    logger.info("Re-triaging ticket %s after customer update", issue_key)

    # Fetch the full issue with all comments
    issue_data = await jira.get_issue(issue_key)
    if not issue_data:
        return

    fields = issue_data.get("fields", {})
    summary = fields.get("summary", "")

    # Build full context: description + all customer comments
    desc_raw = fields.get("description")
    if isinstance(desc_raw, dict):
        description = jira._adf_to_text(desc_raw)
    elif isinstance(desc_raw, str):
        description = desc_raw
    else:
        description = ""

    # Append customer comments to context
    comments = fields.get("comment", {}).get("comments", [])
    customer_messages = [description]
    for c in comments:
        body = c.get("body", {})
        text = jira._adf_to_text(body) if isinstance(body, dict) else str(body)
        if not text or text.startswith("🤖"):
            continue
        # Skip internal comments
        is_internal = False
        for prop in c.get("properties", []):
            if prop.get("key") == "sd.public.comment":
                is_internal = prop.get("value", {}).get("internal", False)
        if not is_internal:
            customer_messages.append(text)

    full_context = "\n\n".join(customer_messages)

    # Re-run triage with full conversation context
    result = await triage_ticket(summary, full_context)

    # Update all fields
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
        intent=result.intent,
        issue_type=result.issue_type,
        language=result.language,
        severity=result.severity,
        information_complete=True,  # Customer provided more info
    )

    # L3 escalation on re-triage
    if result.triage_level == "L3 - Expert":
        await jira.add_label(issue_key, "escalated")
        if result.urgency not in ("Highest", "High"):
            await jira.set_priority(issue_key, "High")
        esc_note = (
            f"ESCALATION: Re-triage elevated this ticket to L3 - Expert.\n\n"
            f"AI confidence: {result.confidence} "
            f"(score: {result.confidence_score:.2f}). "
            f"Department: {result.department}. Severity: {result.severity}.\n"
            f"This ticket requires specialist review."
        )
        await jira.add_comment(issue_key, esc_note, internal=True)
        logger.info("Escalated %s to L3 after re-triage", issue_key)

    logger.info("Re-triaged %s: dept=%s conf=%s", issue_key, result.department, result.confidence)


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
