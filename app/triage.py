"""AI triage engine — delegates everything to the wxO agent.

Sends the raw ticket text to wxO. The agent searches knowledge_base and
resolved_tickets via its tool callbacks, classifies the ticket, and returns
a structured JSON triage result.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from app import wxo

logger = logging.getLogger(__name__)


@dataclass
class TriageResult:
    """Structured triage output — maps directly to Jira custom fields."""

    department: str  # IT, HR, Facilities, Finance, Legal, General
    urgency: str  # Highest, High, Medium, Low, Lowest
    confidence: str  # High, Medium, Low
    triage_level: str  # L1 - Self-Service, L2 - Agent, L3 - Expert
    suggested_response: str  # AI-generated answer
    kb_score: float  # Best cosine similarity from knowledge_base
    kb_match: str  # Best KB article title/summary
    ticket_score: float  # Best cosine similarity from resolved_tickets
    ticket_match: str  # Best resolved ticket summary
    intent: str  # feature_request, bug_report, how_to, access_request, complaint, general_inquiry
    issue_type: str  # context_handling, troubleshooting, configuration, account_management, information, other
    language: str  # en, de, fr, it, etc.
    severity: str  # S1, S2, S3, S4


async def triage_ticket(summary: str, description: str) -> TriageResult:
    """Run the full triage pipeline via the wxO agent.

    The agent will:
    1. Search knowledge_base and resolved_tickets via its tools
    2. Classify the ticket based on search results
    3. Return a structured JSON response
    """
    question = f"{summary}\n\n{description}".strip()

    prompt = _build_triage_prompt(question)
    result = await wxo.chat(message=prompt)
    reply = result.get("reply", "")

    triage = _parse_triage_response(reply)

    logger.info(
        "Triage %s: dept=%s urgency=%s confidence=%s level=%s kb=%.2f ticket=%.2f",
        summary[:50], triage.department, triage.urgency,
        triage.confidence, triage.triage_level, triage.kb_score, triage.ticket_score,
    )

    return triage


def _build_triage_prompt(question: str) -> str:
    """Build a prompt that instructs the wxO agent to search and classify."""
    return f"""Triage this support ticket. You MUST:

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

CONFIDENCE RULES:
- If KB score > 0.7 AND Ticket score > 0.7 -> "High" (documented + solved before)
- If KB score > 0.7 OR Ticket score > 0.7 -> "Medium" (partially matched)
- If both scores < 0.7 -> "Low" (new/unknown issue)

CLASSIFICATION RULES:
- intent: What the user wants (feature_request, bug_report, how_to, access_request, complaint, general_inquiry)
- issue_type: Type of handling needed (context_handling, troubleshooting, configuration, account_management, information, other)
- language: Detect the language of the ticket text (en, de, fr, it, etc.)

If no matches found for a collection, set its score to 0.0 and match to "No match"."""


def _parse_triage_response(reply: str) -> TriageResult:
    """Parse the wxO agent's JSON response into a TriageResult."""
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
        valid_intents = ("feature_request", "bug_report", "how_to", "access_request", "complaint", "general_inquiry")
        if intent not in valid_intents:
            intent = "general_inquiry"

        issue_type = parsed.get("issue_type", "other")
        valid_issue_types = ("context_handling", "troubleshooting", "configuration", "account_management", "information", "other")
        if issue_type not in valid_issue_types:
            issue_type = "other"

        language = parsed.get("language", "en")[:5]
    else:
        # Fallback — agent didn't return valid JSON
        dept = "General"
        urgency = "Medium"
        confidence = "Low"
        triage_level = "L3 - Expert"
        kb_score = 0.0
        kb_match = "No match"
        ticket_score = 0.0
        ticket_match = "No match"
        suggested = reply
        intent = "general_inquiry"
        issue_type = "other"
        language = "en"

    # Map urgency to severity
    severity_map = {"Highest": "S1", "High": "S2", "Medium": "S3", "Low": "S4", "Lowest": "S4"}
    severity = severity_map.get(urgency, "S3")

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
        language=language,
        severity=severity,
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
