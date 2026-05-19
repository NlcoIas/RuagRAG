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
TOP_K            = 3     # Top N similar tickets to retrieve
COSINE_THRESHOLD = 0.8  # Minimum similarity score to pass to LLM check

# ─────────────────────────────────────────
# LLM MODE SWITCH
# ─────────────────────────────────────────
# Option A: Watsonx direct API call (standalone mode)
#   → Set USE_WATSONX_DIRECT = True
#
# Option B: Watsonx Agent handles LLM (agent mode)
#   → Set USE_WATSONX_DIRECT = False
#   → /similarity-only endpoint exposes top-K results for Agent to judge
#   → Agent calls /post-ticket separately after making its own decision
#
USE_WATSONX_DIRECT = True  # ← Toggle here

# Watsonx direct API config (used when USE_WATSONX_DIRECT = True)
WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com")
# WATSONX_MODEL      = "ibm/granite-4-h-small"
WATSONX_MODEL      = "meta-llama/llama-3-3-70b-instruct"

# ─────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────

class NewTicket(BaseModel):
    """
    Complete ticket object passed in after Assembly step.
    Fields may be partially populated — only vectorize_text is strictly required.

    Conversation turns arrive as flat keys (same structure as DB doc):
        user_turn_1, user_turn_2, ... user_turn_N
        assistant_turn_1, assistant_turn_2, ... assistant_turn_N
    Captured via extra="allow"; use get_user_turns() / get_assistant_turns() to access them.
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
    vectorize_text: str              # Required: combined user turns text for embedding

    model_config = {"extra": "allow"}  # captures user_turn_N / assistant_turn_N

    def get_user_turns(self) -> list[tuple[int, str]]:
        """Returns [(1, text), (2, text), ...] sorted by turn number."""
        return sorted(
            [(int(k.split("_")[-1]), v)
             for k, v in self.model_extra.items() if k.startswith("user_turn_")],
            key=lambda x: x[0]
        )

    def get_assistant_turns(self) -> list[tuple[int, str]]:
        """Returns [(1, text), (2, text), ...] sorted by turn number."""
        return sorted(
            [(int(k.split("_")[-1]), v)
             for k, v in self.model_extra.items() if k.startswith("assistant_turn_")],
            key=lambda x: x[0]
        )


class SimilarTicket(BaseModel):
    ticket_id: str
    title: str | None
    similarity: float
    user_turns: list[tuple[int, str]]      # [(1, text), (2, text), ...]
    assistant_turns: list[tuple[int, str]] # [(1, text), (2, text), ...]
    intent: str | None
    issue_type: str | None


class RedundancyResult(BaseModel):
    decision: str           # "POST" | "DISCARD"
    matched_ticket_id: str | None = None
    similarity_scores: list[dict]
    reason: str
    llm_checked: bool       # False if all scores below threshold (skipped LLM)


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def get_headers() -> dict:
    return {"Token": ASTRA_TOKEN, "Content-Type": "application/json"}


def get_watsonx_token() -> str:
    """Exchange WATSONX_API_KEY for a short-lived IAM bearer token."""
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
    """
    Search existing ticket_db using $vectorize (AstraDB handles embedding internally).
    Returns top K results with similarity scores.
    """
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
# [OPTION A] Watsonx direct API — active when USE_WATSONX_DIRECT = True
# [OPTION B] Agent mode      — comment out llm_semantic_check() call in
#                              redundancy_check() and use /similarity-only
#                              + /post-ticket endpoints instead
# ─────────────────────────────────────────

def format_turns(user_turns: list[tuple[int, str]], assistant_turns: list[tuple[int, str]]) -> str:
    """Interleave user/assistant turns into a readable string for the LLM prompt."""
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

    new_turns_text = format_turns(new_ticket.get_user_turns(), new_ticket.get_assistant_turns())

    return f"""You are evaluating whether a new support ticket should be stored in a ticket database.

[NEW TICKET]
- Intent: {new_ticket.intent}
- Issue Type: {new_ticket.issue_type}
- Persona Role: {new_ticket.persona_role}
- Conversation:
{new_turns_text}

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


# [OPTION A] Watsonx direct call
# To switch to Agent mode: comment out this function and
# set USE_WATSONX_DIRECT = False at the top of this file.
def llm_semantic_check(new_ticket: NewTicket, similar_tickets: list[SimilarTicket]) -> dict:
    """
    Call Watsonx API directly to semantically judge redundancy.
    Returns dict with decision, matched_ticket_id, reason.
    """
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

    # debug
    # print(f"[DEBUG] Watsonx URL: {url}")
    # print(f"[DEBUG] PROJECT_ID: {WATSONX_PROJECT_ID}")
    # print(f"[DEBUG] API_KEY exists: {bool(WATSONX_API_KEY)}")

    # try:
    #     token = get_watsonx_token()
    #     print(f"[DEBUG] IAM token OK: {token[:20]}...")
    # except Exception as e:
    #     print(f"[DEBUG] IAM token FAILED: {e}")
    #     raise
    ############

    res = requests.post(url, json=payload, headers=get_watsonx_headers())
    # print(f"[DEBUG] Watsonx status: {res.status_code}")
    # print(f"[DEBUG] Watsonx response: {res.text[:300]}")
    res.raise_for_status()

    raw_text = res.json()["choices"][0]["message"]["content"].strip()
    print(f"[DEBUG] rawtext from Watsonx: {raw_text}")
    if not raw_text:
        raise ValueError(f"LLM returned empty generated_text. Full response: {res.text[:500]}")

    if "```" in raw_text:
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip()

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw_text}")

    return json.loads(match.group())


# ─────────────────────────────────────────
# Step 3: POST to AstraDB (if new)
# ─────────────────────────────────────────

def post_ticket_to_db(new_ticket: NewTicket) -> str:
    """
    Insert the new ticket into ticket_db.
    Uses $vectorize so AstraDB handles embedding automatically.
    Returns inserted document _id.
    """
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"

    # model_extra already contains user_turn_1..N / assistant_turn_1..N as flat keys
    base = {k: v for k, v in new_ticket.model_dump().items()
            if v is not None and k != "vectorize_text"}
    base.update(new_ticket.model_extra)
    base["$vectorize"] = new_ticket.vectorize_text
    doc = base

    payload = {"insertOne": {"document": doc}}

    res = requests.post(url, json=payload, headers=get_headers())
    res.raise_for_status()

    return res.json().get("status", {}).get("insertedIds", [None])[0]


# ─────────────────────────────────────────
# Main Endpoint
# ─────────────────────────────────────────

@app.post("/redundancy-check", response_model=RedundancyResult)
def redundancy_check(new_ticket: NewTicket):
    """
    Full redundancy check pipeline:
    1. Cosine similarity search → top 3 similar tickets
    2. If any score >= threshold:
       - [OPTION A] USE_WATSONX_DIRECT=True  → LLM judges here directly
       - [OPTION B] USE_WATSONX_DIRECT=False → returns similarity results for Agent to judge
    3. POST or DISCARD based on decision
    """

    # Step 1: Vector search
    try:
        raw_docs = vector_search_tickets(new_ticket.vectorize_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AstraDB search error: {e}")

    similar_tickets = [parse_similar_ticket(d) for d in raw_docs]
    similarity_scores = [
        {"ticket_id": t.ticket_id, "title": t.title, "similarity": t.similarity}
        for t in similar_tickets
    ]

    # Step 2: Filter candidates above threshold
    candidates = [t for t in similar_tickets if t.similarity >= COSINE_THRESHOLD]

    if not candidates:
        # All scores below threshold → clearly new, skip LLM
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

    # Step 3: LLM semantic judge
    # [OPTION A] Watsonx direct — comment out if using Agent mode
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

    # [OPTION B] Agent mode — return similarity results without LLM decision
    # Agent reads this response, judges semantics itself,
    # then calls /post-ticket if it decides POST.
    return RedundancyResult(
        decision="PENDING",
        matched_ticket_id=None,
        similarity_scores=similarity_scores,
        reason=f"{len(candidates)} candidate(s) above threshold. Awaiting Agent semantic judgment.",
        llm_checked=False
    )


# ─────────────────────────────────────────
# Agent Mode Endpoints (OPTION B)
# Used when USE_WATSONX_DIRECT = False
# Agent calls /similarity-only to get candidates,
# judges semantics itself, then calls /post-ticket if new.
# ─────────────────────────────────────────

class SimilarityOnlyResponse(BaseModel):
    candidates_above_threshold: list[dict]
    all_similarity_scores: list[dict]
    prompt_for_agent: str   # Ready-to-use prompt Agent can pass directly to its LLM


@app.post("/similarity-only", response_model=SimilarityOnlyResponse)
def similarity_only(new_ticket: NewTicket):
    """
    [OPTION B - Agent mode]
    Returns top-K similarity results + a pre-built prompt for the Agent's LLM.
    Agent uses this to make its own semantic judgment, then calls /post-ticket.
    """
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
         "user_turn_1": t.user_turn_1, "intent": t.intent, "issue_type": t.issue_type}
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
    decision: str           # "POST" | "DISCARD" — Agent's final judgment
    matched_ticket_id: str | None = None
    reason: str


@app.post("/post-ticket", response_model=RedundancyResult)
def post_ticket(req: PostTicketRequest):
    """
    [OPTION B - Agent mode]
    Receives Agent's final decision and executes DB insert if POST.
    """
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
    """Returns raw similarity search results without LLM check or DB insert."""
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