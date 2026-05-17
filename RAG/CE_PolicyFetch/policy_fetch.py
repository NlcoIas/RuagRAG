from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
import asyncio
import httpx

app = FastAPI(
    title="Policy Fetch Tool",
    description="Fetches relevant policy chunks from knowledge_base via vectorize search + gold_doc_ids filter.",
    version="1.0.0"
)

ASTRA_ENDPOINT = os.getenv("ASTRA_DB_ENDPOINT")
ASTRA_TOKEN    = os.getenv("ASTRA_DB_TOKEN")
COLLECTION     = "knowledge_base"
TOP_K          = 5  # Number of vector search results to return


class FetchRequest(BaseModel):
    query: str
    gold_doc_ids: list[str] = []  # gold_doc_ids passed from ticket_search


class PolicyChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    version: str
    content: str
    similarity: float | None = None  # Only vector search results include similarity; filtered results use None
    source: str  # "vector_search" | "gold_doc"


class FetchResponse(BaseModel):
    chunks: list[PolicyChunk]
    count: int


HEADERS = {"Token": ASTRA_TOKEN, "Content-Type": "application/json"} if ASTRA_TOKEN else {}


def get_headers():
    return {"Token": ASTRA_TOKEN, "Content-Type": "application/json"}


def vectorize_search(query: str) -> list[dict]:
    """Run vectorize search against knowledge_base using the user query."""
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
    payload = {
        "find": {
            "sort": {"$vectorize": query},
            "options": {"limit": TOP_K, "includeSimilarity": True}
        }
    }
    res = requests.post(url, json=payload, headers=get_headers())
    res.raise_for_status()
    return res.json().get("data", {}).get("documents", [])

    
def gold_doc_search(doc_ids: list[str]) -> list[dict]:
    if not doc_ids:
        return []

    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
    all_docs = []

    for doc_id in doc_ids:
        payload = {
            "find": {
                "filter": {"doc_id": doc_id},
                "options": {"limit": 3}
            }
        }
        res = requests.post(url, json=payload, headers=get_headers())
        res.raise_for_status()
        docs = res.json().get("data", {}).get("documents", [])
        all_docs.extend(docs)

    return all_docs

#### AstraDB doen't use $in ####
# def gold_doc_search(doc_ids: list[str]) -> list[dict]:
#     """Query knowledge_base using the gold_doc_ids filter."""
#     if not doc_ids:
#         return []

#     url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"

#     # Query multiple doc_id values in one request using $in
#     payload = {
#         "find": {
#             "filter": {"doc_id": {"$in": doc_ids}},
#             "options": {"limit": TOP_K}
#         }
#     }
#     res = requests.post(url, json=payload, headers=get_headers())
#     res.raise_for_status()
#     return res.json().get("data", {}).get("documents", [])

def parse_chunk(doc: dict, source: str) -> PolicyChunk:
    return PolicyChunk(
        chunk_id=doc.get("chunk_id", doc.get("_id", "")),
        doc_id=doc.get("doc_id", ""),
        title=doc.get("title", ""),
        version=doc.get("version", "unknown"),
        content=doc.get("content", ""),
        similarity=doc.get("$similarity"),
        source=source,
    )


def deduplicate(chunks: list[PolicyChunk]) -> list[PolicyChunk]:
    """Remove duplicates by chunk_id. Prefer vector_search entries because they include similarity."""
    seen = {}
    for chunk in chunks:
        key = f"{chunk.doc_id}:{chunk.chunk_id}"  
        if key not in seen:
            seen[key] = chunk
        # if chunk.chunk_id not in seen:
        #     seen[chunk.chunk_id] = chunk
        else:
            # If a duplicate exists, keep the vector_search version to preserve similarity
            if chunk.source == "vector_search":
                seen[key] = chunk
                # seen[chunk.chunk_id] = chunk
    return list(seen.values())


def sort_by_version_then_similarity(chunks: list[PolicyChunk]) -> list[PolicyChunk]:
    """Sort by version descending, then by similarity descending within the same version."""
    def sort_key(c: PolicyChunk):
        sim = c.similarity if c.similarity is not None else 0.0
        return (c.version, sim)

    return sorted(chunks, key=sort_key, reverse=True)


@app.post("/fetch-policy", response_model=FetchResponse)
def fetch_policy(req: FetchRequest):
    try:
        # Run both searches
        vector_docs = vectorize_search(req.query)
        gold_docs   = gold_doc_search(req.gold_doc_ids)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AstraDB error: {e}")

    vector_chunks = [parse_chunk(d, "vector_search") for d in vector_docs]
    gold_chunks   = [parse_chunk(d, "gold_doc") for d in gold_docs]

    # Merge, deduplicate, then sort by version/similarity
    all_chunks = deduplicate(vector_chunks + gold_chunks)
    all_chunks = sort_by_version_then_similarity(all_chunks)

    return FetchResponse(chunks=all_chunks, count=len(all_chunks))


@app.get("/health")
def health():
    return {"status": "ok"}
