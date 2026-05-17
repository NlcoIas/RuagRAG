from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os

app = FastAPI(
    title="Ticket Search Tool",
    description="Searches ticket_db for similar past cases and returns gold_doc_ids for policy resolution.",
    version="2.0.0"
)

ASTRA_ENDPOINT = os.getenv("ASTRA_DB_ENDPOINT")
ASTRA_TOKEN    = os.getenv("ASTRA_DB_TOKEN")
COLLECTION     = "ticket_db"
TOP_N          = 3


class SearchRequest(BaseModel):
    query: str


class TicketResult(BaseModel):
    ticket_id: str
    title: str
    similarity: float
    rating: int | None
    gold_doc_ids: str | None
    user_turns: list[str]
    assistant_turns: list[str]


class SearchResponse(BaseModel):
    tickets: list[TicketResult]
    count: int


def search_astradb(query: str) -> list:
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
    payload = {
        "find": {
            "sort": {"$vectorize": query},
            "options": {"limit": TOP_N, "includeSimilarity": True}
        }
    }
    headers = {"Token": ASTRA_TOKEN, "Content-Type": "application/json"}
    res = requests.post(url, json=payload, headers=headers)
    print("Astra status:", res.status_code)
    print("Astra response:", res.text[:500])
    res.raise_for_status()
    return res.json().get("data", {}).get("documents", [])


def parse_ticket(doc: dict) -> TicketResult:
    user_turns = [
        v for k, v in doc.items()
        if k.startswith("user_turn_") and v
    ]
    assistant_turns = [
        v for k, v in doc.items()
        if k.startswith("assistant_turn_") and v
    ]
    return TicketResult(
        ticket_id=doc.get("_id", ""),
        title=doc.get("title", ""),
        similarity=doc.get("$similarity", 0.0),
        rating=doc.get("rating"),
        gold_doc_ids=doc.get("gold_doc_ids"),
        user_turns=user_turns,
        assistant_turns=assistant_turns,
    )


@app.post("/search-tickets", response_model=SearchResponse)
def search_tickets(req: SearchRequest):
    try:
        docs = search_astradb(req.query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AstraDB error: {e}")

    tickets = [parse_ticket(doc) for doc in docs]
    return SearchResponse(tickets=tickets, count=len(tickets))


@app.get("/health")
def health():
    return {"status": "ok"}

# from fastapi import FastAPI
# from pydantic import BaseModel
# import requests
# import os

# app = FastAPI()

# ASTRA_ENDPOINT = os.getenv("ASTRA_DB_ENDPOINT")
# ASTRA_TOKEN    = os.getenv("ASTRA_DB_TOKEN")
# WX_BASE_URL    = os.getenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com")  # base URL
# WX_API_KEY     = os.getenv("WATSONX_API_KEY")
# WX_PROJECT_ID  = os.getenv("WATSONX_PROJECT_ID")
# COLLECTION     = "ticket_db"
# TOP_N          = 3
# RELEVANCE_THRESHOLD = 0.6

# WX_MODEL_ID = "meta-llama/llama-3-3-70b-instruct"

# WX_GENERATION_URL = f"{WX_BASE_URL.rstrip('/')}/ml/v1/text/generation?version=2024-05-01"

# class SearchRequest(BaseModel):
#     query: str

# def search_astradb(query: str) -> list:
#     url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
#     payload = {
#         "find": {
#             "sort": {"$vectorize": query},
#             "options": {"limit": TOP_N, "includeSimilarity": True}
#         }
#     }
#     headers = {"Token": ASTRA_TOKEN, "Content-Type": "application/json"}
#     res = requests.post(url, json=payload, headers=headers)
#     print("Astra status:", res.status_code)
#     print("Astra response:", res.text[:500])
#     res.raise_for_status()
#     return res.json().get("data", {}).get("documents", [])

# def get_wx_token() -> str:
#     res = requests.post(
#         "https://iam.cloud.ibm.com/identity/token",
#         data={
#             "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
#             "apikey": WX_API_KEY
#         }
#     )
#     print("IAM status:", res.status_code)
#     res.raise_for_status()
#     return res.json()["access_token"]

# def check_semantic_relevance(query: str, ticket: dict) -> float:
#     token = get_wx_token()

#     user_turns = " | ".join(
#         v for k, v in ticket.items()
#         if k.startswith("user_turn_") and v
#     )
#     assistant_turns = " | ".join(
#         v for k, v in ticket.items()
#         if k.startswith("assistant_turn_") and v
#     )

#     prompt = f"""You are a relevance evaluator.
# Given a user query and a historical support ticket, score the semantic relevance from 0.0 to 1.0.

# Query: {query}

# Ticket user turns: {user_turns}
# Ticket assistant turns: {assistant_turns}

# Respond with ONLY a float between 0.0 and 1.0. Nothing else."""

#     payload = {
#         "model_id": WX_MODEL_ID,
#         "project_id": WX_PROJECT_ID,
#         "input": prompt,
#         "parameters": {"max_new_tokens": 5, "temperature": 0}
#     }
#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json"
#     }

#     print("watsonx url:", WX_GENERATION_URL)
#     res = requests.post(WX_GENERATION_URL, json=payload, headers=headers)
#     print("watsonx status:", res.status_code)
#     print("watsonx response:", res.text[:1000])
#     res.raise_for_status()

#     try:
#         score_str = res.json()["results"][0]["generated_text"].strip()
#         return float(score_str)
#     except Exception as e:
#         print("Score parse error:", e)
#         return 0.0

# @app.post("/search-tickets")
# def search_tickets(req: SearchRequest):
#     candidates = search_astradb(req.query)
#     results = []
#     for ticket in candidates:
#         score = check_semantic_relevance(req.query, ticket)
#         if score >= RELEVANCE_THRESHOLD:
#             ticket["semantic_relevance_score"] = score
#             results.append(ticket)
#     return {"tickets": results, "count": len(results)}

# @app.get("/health")
# def health():
#     return {"status": "ok"}