"""AI triage engine — sends structured JSON to the Gate Agent.

The Gate Agent pipeline:
1. Translates user messages to English
2. Checks if required information is complete
3. Searches knowledge_base and resolved_tickets via RAG Agent
4. Generates response in user's language
5. Returns structured JSON with all fields

If the Gate Agent fails, falls back to the RAG Agent with a direct prompt.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from app import wxo

logger = logging.getLogger(__name__)

# Input Gate — flow-based agent, returns processed input_json via thread messages
INPUT_GATE_ID = "e4bedbf4-2419-4a0a-9def-9cc354909165"
# Gate Agent — standard agent, returns directly via run polling (fallback)
GATE_AGENT_ID = "d7266dbb-c6b9-4c72-b981-6d3603160001"
# RAG Agent — direct triage without translation pipeline (fallback)
RAG_AGENT_ID = "00e12daf-67b5-426b-a1e9-4cee6cb4ee77"


@dataclass
class TriageResult:
    """Structured triage output — maps directly to Jira custom fields."""

    department: str  # IT, HR, Facilities, Finance, Legal, General
    urgency: str  # Highest, High, Medium, Low, Lowest
    confidence: str  # High, Medium, Low
    triage_level: str  # L1 - Self-Service, L2 - Agent, L3 - Expert
    suggested_response: str  # AI-generated answer (in user's language)
    kb_score: float  # Best cosine similarity from knowledge_base
    kb_match: str  # Best KB article title/summary
    ticket_score: float  # Best cosine similarity from resolved_tickets
    ticket_match: str  # Best resolved ticket summary
    intent: str  # feature_request, bug_report, how_to, access_request, complaint, general_inquiry
    issue_type: str  # context_handling, troubleshooting, configuration, account_management, information, other
    language: str  # en, de, fr, it, etc.
    severity: str  # S1, S2, S3, S4
    information_complete: bool  # Whether enough info was provided
    confidence_score: float  # Raw confidence 0.0-1.0 from Gate Agent


async def triage_ticket(summary: str, description: str) -> TriageResult:
    """Run the full triage pipeline via the Gate Agent.

    Tries the Gate Agent first (translation + info check + RAG).
    Falls back to RAG Agent with direct prompt if Gate Agent fails.
    """
    question = f"{summary}\n\n{description}".strip()

    # Try Gate Agent first
    try:
        result = await _triage_via_gate_agent(summary, question)
        if result:
            return result
    except Exception as exc:
        logger.warning("Gate Agent failed, falling back to RAG Agent: %s", exc)

    # Fallback to RAG Agent with direct prompt
    return await _triage_via_rag_agent(question, summary)


async def _triage_via_gate_agent(summary: str, question: str) -> TriageResult | None:
    """Send structured JSON to the Input Gate and parse the processed input_json."""

    # Build the Input Gate input format
    gate_input = {
        "original_input_message": [
            {"role": "user", "content": question}
        ],
        "english_input_message": "None",
        "language": "None",
        "classification": {
            "department": "None",
            "urgency": "None",
            "intent": "None",
            "issue_type": "None",
            "severity": "None",
        },
        "rag_search": {
            "tickets": "None",
            "policies": "None",
        },
        "response": {
            "original_response_user": "None",
            "translated_response_user": "None",
            "response_customer_service_message": "None",
        },
        "triage": {
            "confidence": "None",
            "triage_level": "None",
            "information_complete": False,
        },
    }

    # Send to Input Gate via flow-based chat (reads thread messages for result)
    message = json.dumps(gate_input, ensure_ascii=False)
    result = await wxo.chat_flow(message=message, agent_id=INPUT_GATE_ID, max_wait=120)
    parsed = result.get("reply", {})

    # If Input Gate failed, fall back directly (Gate Agent also takes too long)
    if not parsed or not isinstance(parsed, dict):
        logger.info("Input Gate returned no data, falling back to RAG Agent")
        return None

    # Extract language
    language = parsed.get("language") or "en"
    if language == "None":
        language = "en"

    # Extract response — prefer translated (user's language)
    response = parsed.get("response", {})
    if not isinstance(response, dict):
        response = {}
    suggested = (
        response.get("translated_response_user")
        or response.get("original_response_user")
        or parsed.get("translated_response_user")
        or parsed.get("original_response_user")
        or ""
    )
    if not suggested or suggested == "None":
        return None

    # Triage fields
    triage = parsed.get("triage", {})
    if isinstance(triage, str):
        triage = {}

    # Confidence — Gate Agent returns float 0-1
    raw_confidence = triage.get("confidence", 0.0)
    if isinstance(raw_confidence, (int, float)):
        confidence_score = float(raw_confidence)
        confidence = "High" if confidence_score > 0.7 else "Medium" if confidence_score > 0.4 else "Low"
    elif raw_confidence in ("High", "Medium", "Low"):
        confidence = raw_confidence
        confidence_score = {"High": 0.85, "Medium": 0.55, "Low": 0.2}.get(raw_confidence, 0.0)
    else:
        confidence = "Low"
        confidence_score = 0.0

    raw_triage_level = triage.get("triage_level", "None")
    # Map Gate Agent's format to our Jira field options
    triage_level_map = {
        "L1 - LLM": "L1 - Self-Service",
        "L1 - Self-Service": "L1 - Self-Service",
        "L2 - Agent": "L2 - Agent",
        "L3 - Expert": "L3 - Expert",
    }
    triage_level = triage_level_map.get(raw_triage_level, _confidence_to_triage(confidence))

    info_complete = triage.get("information_complete", False)
    if isinstance(info_complete, str):
        info_complete = info_complete.lower() == "true"

    # Classification — Gate Agent may not fill these yet, we derive defaults
    classification = parsed.get("classification", {})
    if isinstance(classification, str):
        classification = {}

    dept = classification.get("department", "General")
    if dept == "None" or dept not in ("IT", "HR", "Facilities", "Finance", "Legal", "General"):
        dept = "General"

    urgency = classification.get("urgency", "Medium")
    if urgency == "None" or urgency not in ("Highest", "High", "Medium", "Low", "Lowest"):
        urgency = "Medium"

    intent = classification.get("intent", "general_inquiry")
    valid_intents = ("feature_request", "bug_report", "how_to", "access_request", "complaint", "general_inquiry")
    if intent == "None" or intent not in valid_intents:
        intent = "general_inquiry"

    issue_type = classification.get("issue_type", "other")
    valid_issue_types = ("context_handling", "troubleshooting", "configuration", "account_management", "information", "other")
    if issue_type == "None" or issue_type not in valid_issue_types:
        issue_type = "other"

    severity = classification.get("severity", "None")
    if severity == "None" or severity not in ("S1", "S2", "S3", "S4"):
        severity_map = {"Highest": "S1", "High": "S2", "Medium": "S3", "Low": "S4", "Lowest": "S4"}
        severity = severity_map.get(urgency, "S3")

    # RAG search results
    rag = parsed.get("rag_search", {})
    if isinstance(rag, str):
        rag = {}

    # Extract scores from RAG results
    kb_score = 0.0
    kb_match = "No match"
    ticket_score = 0.0
    ticket_match = "No match"

    policies = rag.get("policies")
    if policies and policies != "None" and isinstance(policies, list) and len(policies) > 0:
        top = policies[0] if isinstance(policies[0], dict) else {}
        kb_score = float(top.get("policy_score", top.get("score", top.get("similarity", 0))))
        kb_match = str(top.get("policy_title", top.get("title", top.get("text", "KB match"))))[:200]
    elif policies and policies != "None" and isinstance(policies, str):
        kb_match = policies[:200]

    tickets = rag.get("tickets")
    if tickets and tickets != "None" and isinstance(tickets, list) and len(tickets) > 0:
        top = tickets[0] if isinstance(tickets[0], dict) else {}
        ticket_score = float(top.get("ticket_score", top.get("score", top.get("similarity", 0))))
        ticket_match = str(top.get("ticket_title", top.get("title", top.get("text", "Ticket match"))))[:200]
    elif tickets and tickets != "None" and isinstance(tickets, str):
        ticket_match = tickets[:200]

    logger.info(
        "Gate Agent triage %s: lang=%s conf=%s info_complete=%s dept=%s",
        summary[:50], language, confidence, info_complete, dept,
    )

    return TriageResult(
        department=dept,
        urgency=urgency,
        confidence=confidence,
        triage_level=triage_level,
        suggested_response=suggested,
        kb_score=round(kb_score, 4),
        kb_match=kb_match,
        ticket_score=round(ticket_score, 4),
        ticket_match=ticket_match,
        intent=intent,
        issue_type=issue_type,
        language=language[:5],
        severity=severity,
        information_complete=info_complete,
        confidence_score=round(confidence_score, 4),
    )


async def _triage_via_rag_agent(question: str, summary: str) -> TriageResult:
    """Fallback: use RAG Agent directly with structured prompt."""
    prompt = f"""Triage this support ticket. You MUST:

1. Search the knowledge base for relevant documents
2. Search resolved tickets for similar past cases
3. Classify the ticket based on what you find

TICKET:
{question}

After searching, respond with EXACTLY this JSON format (no other text):
{{
  "department": "IT|HR|Facilities|Finance|Legal|General",
  "urgency": "Highest|High|Medium|Low|Lowest",
  "confidence": "High|Medium|Low",
  "triage_level": "L1 - Self-Service|L2 - Agent|L3 - Expert",
  "suggested_response": "Your detailed response based on the search results...",
  "kb_score": 0.85,
  "kb_match": "Brief summary of best knowledge base match",
  "ticket_score": 0.72,
  "ticket_match": "Brief summary of best resolved ticket match",
  "intent": "feature_request|bug_report|how_to|access_request|complaint|general_inquiry",
  "issue_type": "context_handling|troubleshooting|configuration|account_management|information|other",
  "language": "en|de|fr|it"
}}

If no matches found for a collection, set its score to 0.0 and match to "No match"."""

    result = await wxo.chat(message=prompt, agent_id=RAG_AGENT_ID)
    reply = result.get("reply", "")
    parsed = _extract_json(reply)

    if parsed:
        dept = parsed.get("department", "General")
        if dept not in ("IT", "HR", "Facilities", "Finance", "Legal", "General"):
            dept = "General"
        urgency = parsed.get("urgency", "Medium")
        if urgency not in ("Highest", "High", "Medium", "Low", "Lowest"):
            urgency = "Medium"
        confidence = parsed.get("confidence", "Low")
        if confidence not in ("High", "Medium", "Low"):
            confidence = "Low"
        triage_level = parsed.get("triage_level", "L3 - Expert")
        if triage_level not in ("L1 - Self-Service", "L2 - Agent", "L3 - Expert"):
            triage_level = _confidence_to_triage(confidence)
        try:
            kb_score = float(parsed.get("kb_score", 0.0))
        except (TypeError, ValueError):
            kb_score = 0.0
        kb_match = str(parsed.get("kb_match", "No match"))[:200]
        try:
            ticket_score = float(parsed.get("ticket_score", 0.0))
        except (TypeError, ValueError):
            ticket_score = 0.0
        ticket_match = str(parsed.get("ticket_match", "No match"))[:200]
        suggested = parsed.get("suggested_response", reply)
        intent = parsed.get("intent", "general_inquiry")
        if intent not in ("feature_request", "bug_report", "how_to", "access_request", "complaint", "general_inquiry"):
            intent = "general_inquiry"
        issue_type = parsed.get("issue_type", "other")
        if issue_type not in ("context_handling", "troubleshooting", "configuration", "account_management", "information", "other"):
            issue_type = "other"
        language = parsed.get("language", "en")[:5]
    else:
        dept, urgency, confidence, triage_level = "General", "Medium", "Low", "L3 - Expert"
        kb_score, kb_match, ticket_score, ticket_match = 0.0, "No match", 0.0, "No match"
        suggested, intent, issue_type, language = reply, "general_inquiry", "other", "en"

    severity_map = {"Highest": "S1", "High": "S2", "Medium": "S3", "Low": "S4", "Lowest": "S4"}

    return TriageResult(
        department=dept, urgency=urgency, confidence=confidence, triage_level=triage_level,
        suggested_response=suggested, kb_score=round(kb_score, 4), kb_match=kb_match,
        ticket_score=round(ticket_score, 4), ticket_match=ticket_match,
        intent=intent, issue_type=issue_type, language=language,
        severity=severity_map.get(urgency, "S3"),
        information_complete=True,
        confidence_score=0.0,
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from text that may contain other content."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _confidence_to_triage(confidence: str) -> str:
    """Map confidence to default triage level."""
    if confidence == "High":
        return "L1 - Self-Service"
    if confidence == "Medium":
        return "L2 - Agent"
    return "L3 - Expert"
