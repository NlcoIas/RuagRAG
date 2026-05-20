from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
import json
import re
load_dotenv()

app = FastAPI(
    title="Redundancy Check",
    description="Checks whether a new support ticket is semantically redundant against existing tickets in AstraDB.",
    version="1.0.0"
)

ASTRA_ENDPOINT   = os.getenv("ASTRA_DB_ENDPOINT")
ASTRA_TOKEN      = os.getenv("ASTRA_DB_TOKEN")
COLLECTION       = "ticket_db"
TOP_K            = 3
COSINE_THRESHOLD = 0.8

USE_WATSONX_DIRECT = True

WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com")
WATSONX_MODEL      = "meta-llama/llama-3-3-70b-instruct"


# ─────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────

class NewTicket(BaseModel):
    """
    The conversation field receives the full dialogue as a single string for Agent compatibility.
    Format: "User: ...\nAssistant: ...\nUser: ...\nAssistant: ..."
    When saved to the DB, it is parsed into user_turn_N / assistant_turn_N fields.
    For local testing, flat user_turn_1 / assistant_turn_1 fields are still allowed via extra="allow".
    """
    title: str | None = None
    intent: str | None = None
    issue_type: str | None = None
    severity: str | None = None
    urgency: str | None = None
    language: str | None = None
    persona_role: str | None = None
    persona_access_tier: str | None = None
    gold_doc_ids: str | None = None
    vectorize_text: str
    conversation: str | None = None  # Agent input format: "User: ...\nAssistant: ..."

    model_config = {"extra": "allow"}  # Allow user_turn_N / assistant_turn_N fields for local testing

    def get_user_turns(self) -> list[tuple[int, str]]:
        return sorted(
            [(int(k.split("_")[-1]), v)
             for k, v in self.model_extra.items() if k.startswith("user_turn_")],
            key=lambda x: x[0]
        )

    def get_assistant_turns(self) -> list[tuple[int, str]]:
        return sorted(
            [(int(k.split("_")[-1]), v)
             for k, v in self.model_extra.items() if k.startswith("assistant_turn_")],
            key=lambda x: x[0]
        )

    def get_conversation_str(self) -> str:
        """
        Use the conversation field as-is when it is provided for the Agent path.
        Otherwise, compose the conversation from flat user_turn_N / assistant_turn_N fields for local testing.
        """
        if self.conversation:
            return self.conversation

        user_turns = self.get_user_turns()
        if not user_turns:
            return "(no conversation)"

        asst_map = {n: text for n, text in self.get_assistant_turns()}
        lines = []
        for n, text in user_turns:
            lines.append(f"User: {text}")
            if n in asst_map:
                lines.append(f"Assistant: {asst_map[n]}")
        return "\n".join(lines)


def parse_conversation_to_turns(conversation: str) -> dict:
    """
    Parse a "User: ...\nAssistant: ..." formatted string into a flat dict:
    {"user_turn_1": ..., "assistant_turn_1": ...}.
    Used when saving to the DB.
    """
    turns = {}
    user_count = 0
    assistant_count = 0

    for line in conversation.strip().split("\n"):
        line = line.strip()
        if line.lower().startswith("user:"):
            user_count += 1
            turns[f"user_turn_{user_count}"] = line[5:].strip()
        elif line.lower().startswith("assistant:"):
            assistant_count += 1
            turns[f"assistant_turn_{assistant_count}"] = line[10:].strip()

    return turns


class SimilarTicket(BaseModel):
    ticket_id: str
    title: str | None
    similarity: float
    user_turns: list[tuple[int, str]]
    assistant_turns: list[tuple[int, str]]
    intent: str | None
    issue_type: str | None


class RedundancyResult(BaseModel):
    decision: str
    matched_ticket_id: str | None = None
    similarity_scores: list[dict]
    reason: str
    llm_checked: bool


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def get_headers() -> dict:
    return {"Token": ASTRA_TOKEN, "Content-Type": "application/json"}


def get_watsonx_token() -> str:
    res = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": WATSONX_API_KEY
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    res.raise_for_status()
    return res.json()["access_token"]


def get_watsonx_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_watsonx_token()}",
        "Content-Type": "application/json"
    }


# ─────────────────────────────────────────
# Step 1: Cosine Similarity Search (AstraDB)
# ─────────────────────────────────────────

def vector_search_tickets(vectorize_text: str) -> list[dict]:
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
    payload = {
        "find": {
            "sort": {"$vectorize": vectorize_text},
            "options": {
                "limit": TOP_K,
                "includeSimilarity": True
            }
        }
    }
    res = requests.post(url, json=payload, headers=get_headers())
    res.raise_for_status()
    return res.json().get("data", {}).get("documents", [])


def parse_similar_ticket(doc: dict) -> SimilarTicket:
    """Parse flat user_turn_N / assistant_turn_N fields from a DB document into lists."""
    user_turns = sorted(
        [(int(k.split("_")[-1]), v)
         for k, v in doc.items() if k.startswith("user_turn_")],
        key=lambda x: x[0]
    )
    assistant_turns = sorted(
        [(int(k.split("_")[-1]), v)
         for k, v in doc.items() if k.startswith("assistant_turn_")],
        key=lambda x: x[0]
    )
    return SimilarTicket(
        ticket_id=doc.get("_id", ""),
        title=doc.get("title"),
        similarity=doc.get("$similarity", 0.0),
        user_turns=user_turns,
        assistant_turns=assistant_turns,
        intent=doc.get("intent"),
        issue_type=doc.get("issue_type")
    )


# ─────────────────────────────────────────
# Step 2: LLM Semantic Judge
# ─────────────────────────────────────────

def format_turns(user_turns: list[tuple[int, str]], assistant_turns: list[tuple[int, str]]) -> str:
    """Convert SimilarTicket turn lists into the prompt string format."""
    if not user_turns:
        return "  (no conversation turns)"
    asst_map = {n: text for n, text in assistant_turns}
    lines = []
    for n, text in user_turns:
        lines.append(f"  User Turn {n}: {text}")
        if n in asst_map:
            lines.append(f"  Assistant Turn {n}: {asst_map[n]}")
    return "\n".join(lines)


def build_llm_prompt(new_ticket: NewTicket, similar_tickets: list[SimilarTicket]) -> str:
    existing = ""
    for i, t in enumerate(similar_tickets, 1):
        existing += f"""
[Existing Ticket {i}]
- ID: {t.ticket_id}
- Title: {t.title}
- Intent: {t.intent}
- Issue Type: {t.issue_type}
- Cosine Similarity: {t.similarity:.4f}
- Conversation:
{format_turns(t.user_turns, t.assistant_turns)}
"""

    new_conversation = new_ticket.get_conversation_str()

    return f"""You are evaluating whether a new support ticket should be stored in a ticket database.

[NEW TICKET]
- Intent: {new_ticket.intent}
- Issue Type: {new_ticket.issue_type}
- Persona Role: {new_ticket.persona_role}
- Conversation:
{new_conversation}

[EXISTING TICKETS - Top {len(similar_tickets)} by cosine similarity]
{existing}

Evaluation is a two-step process:

STEP 1 — Is the user's question substantively the same as an existing ticket?
- Compare only the user turns of the new ticket against existing tickets
- "Same" means the core problem being asked is identical, not just similar wording
- If NO existing ticket asks the same core question → POST immediately, skip Step 2

STEP 2 — (Only if Step 1 found a match) Is the assistant's answer new?
- Compare the assistant turns of the new ticket against the matched existing ticket
- DISCARD if the answer conveys the same resolution, even if rephrased
- POST if the answer contains ANY of the following:
  - Different resolution steps
  - Updated policy or changed access rules
  - New constraints or conditions
  - Different outcome due to system/environment change
- If NONE of the above apply → DISCARD
- Ignore completely: persona role, tone, writing style, severity, urgency, language

Respond ONLY with a JSON object. No explanation outside the JSON.
{{
  "decision": "POST" or "DISCARD",
  "matched_ticket_id": "<id or null>",
  "reason": "<max one sentence within 30 words>"
}}"""


def extract_json(text: str) -> dict:
    """Extract the first complete JSON object by tracking brace depth."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON found: {text}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])
    raise ValueError(f"Unmatched braces in: {text}")


def llm_semantic_check(new_ticket: NewTicket, similar_tickets: list[SimilarTicket]) -> dict:
    prompt = build_llm_prompt(new_ticket, similar_tickets)

    url = f"{WATSONX_URL}/ml/v1/text/chat?version=2023-05-29"
    payload = {
        "model_id": WATSONX_MODEL,
        "project_id": WATSONX_PROJECT_ID,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "parameters": {
            "max_new_tokens": 300
        }
    }

    res = requests.post(url, json=payload, headers=get_watsonx_headers())
    res.raise_for_status()

    raw_text = res.json()["choices"][0]["message"]["content"].strip()
    print(f"[DEBUG] rawtext from Watsonx: {raw_text}")

    if not raw_text:
        raise ValueError(f"LLM returned empty response: {res.text[:500]}")

    if "```" in raw_text:
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip()

    return extract_json(raw_text)


# ─────────────────────────────────────────
# Step 3: POST to AstraDB (if new)
# ─────────────────────────────────────────

def post_ticket_to_db(new_ticket: NewTicket) -> str:
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"

    base = {k: v for k, v in new_ticket.model_dump().items()
            if v is not None and k not in ("vectorize_text", "conversation")}

    # Parse the conversation string into flat fields before saving, if provided
    if new_ticket.conversation:
        base.update(parse_conversation_to_turns(new_ticket.conversation))
    else:
        # Existing local test path: save user_turn_N / assistant_turn_N from model_extra as-is
        base.update(new_ticket.model_extra)

    base["$vectorize"] = new_ticket.vectorize_text
    payload = {"insertOne": {"document": base}}

    res = requests.post(url, json=payload, headers=get_headers())
    res.raise_for_status()
    return res.json().get("status", {}).get("insertedIds", [None])[0]


# ─────────────────────────────────────────
# Main Endpoint
# ─────────────────────────────────────────

@app.post("/redundancy-check", response_model=RedundancyResult)
def redundancy_check(new_ticket: NewTicket):
    try:
        raw_docs = vector_search_tickets(new_ticket.vectorize_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AstraDB search error: {e}")

    similar_tickets = [parse_similar_ticket(d) for d in raw_docs]
    similarity_scores = [
        {"ticket_id": t.ticket_id, "title": t.title, "similarity": t.similarity}
        for t in similar_tickets
    ]

    candidates = [t for t in similar_tickets if t.similarity >= COSINE_THRESHOLD]

    if not candidates:
        try:
            post_ticket_to_db(new_ticket)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AstraDB insert error: {e}")

        return RedundancyResult(
            decision="POST",
            matched_ticket_id=None,
            similarity_scores=similarity_scores,
            reason="All cosine similarity scores below threshold. Clearly new ticket.",
            llm_checked=False
        )

    if USE_WATSONX_DIRECT:
        try:
            llm_result = llm_semantic_check(new_ticket, candidates)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM check error: {e}")

        decision   = llm_result.get("decision", "POST")
        matched_id = llm_result.get("matched_ticket_id")
        reason     = llm_result.get("reason", "")

        if decision == "POST":
            try:
                post_ticket_to_db(new_ticket)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"AstraDB insert error: {e}")

        return RedundancyResult(
            decision=decision,
            matched_ticket_id=matched_id,
            similarity_scores=similarity_scores,
            reason=reason,
            llm_checked=True
        )

    return RedundancyResult(
        decision="PENDING",
        matched_ticket_id=None,
        similarity_scores=similarity_scores,
        reason=f"{len(candidates)} candidate(s) above threshold. Awaiting Agent semantic judgment.",
        llm_checked=False
    )


# ─────────────────────────────────────────
# Agent Mode Endpoints (OPTION B)
# ─────────────────────────────────────────

class SimilarityOnlyResponse(BaseModel):
    candidates_above_threshold: list[dict]
    all_similarity_scores: list[dict]
    prompt_for_agent: str


@app.post("/similarity-only", response_model=SimilarityOnlyResponse)
def similarity_only(new_ticket: NewTicket):
    try:
        raw_docs = vector_search_tickets(new_ticket.vectorize_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AstraDB search error: {e}")

    similar_tickets = [parse_similar_ticket(d) for d in raw_docs]
    candidates = [t for t in similar_tickets if t.similarity >= COSINE_THRESHOLD]

    all_scores = [
        {"ticket_id": t.ticket_id, "title": t.title, "similarity": t.similarity}
        for t in similar_tickets
    ]
    candidates_out = [
        {"ticket_id": t.ticket_id, "title": t.title, "similarity": t.similarity,
         "conversation": format_turns(t.user_turns, t.assistant_turns),
         "intent": t.intent, "issue_type": t.issue_type}
        for t in candidates
    ]

    prompt = build_llm_prompt(new_ticket, candidates) if candidates else "No candidates above threshold."

    return SimilarityOnlyResponse(
        candidates_above_threshold=candidates_out,
        all_similarity_scores=all_scores,
        prompt_for_agent=prompt
    )


class PostTicketRequest(BaseModel):
    ticket: NewTicket
    decision: str
    matched_ticket_id: str | None = None
    reason: str


@app.post("/post-ticket", response_model=RedundancyResult)
def post_ticket(req: PostTicketRequest):
    if req.decision == "POST":
        try:
            post_ticket_to_db(req.ticket)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AstraDB insert error: {e}")

    return RedundancyResult(
        decision=req.decision,
        matched_ticket_id=req.matched_ticket_id,
        similarity_scores=[],
        reason=req.reason,
        llm_checked=True
    )


# ─────────────────────────────────────────
# Health & Debug
# ─────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/debug-similarity")
def debug_similarity(new_ticket: NewTicket):
    try:
        raw_docs = vector_search_tickets(new_ticket.vectorize_text)
    except Exception as e:
        return {"error": str(e)}

    return {
        "top_k": TOP_K,
        "threshold": COSINE_THRESHOLD,
        "results": [
            {
                "ticket_id": d.get("_id"),
                "title": d.get("title"),
                "similarity": d.get("$similarity"),
                "user_turn_1": d.get("user_turn_1")
            }
            for d in raw_docs
        ]
    }
