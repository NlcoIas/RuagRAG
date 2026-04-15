"""Astra DB service — connect, search, and ingest documents.

Uses server-side NVIDIA NV-Embed-QA embeddings via $vectorize.
No local embedding model needed.
"""

import logging
from typing import Any

from astrapy import Collection, DataAPIClient

from app.config import ASTRA_DB_ENDPOINT, ASTRA_DB_TOKEN

logger = logging.getLogger(__name__)

# Max chars for $vectorize (NV-Embed-QA has ~512 token window)
MAX_VECTORIZE_CHARS = 2000

# Singleton — initialized on first call
_collection: Collection | None = None


def _get_collection() -> Collection:
    """Return the Astra DB collection handle. Connects on first call."""
    global _collection
    if _collection is not None:
        return _collection

    client = DataAPIClient(ASTRA_DB_TOKEN)
    database = client.get_database_by_api_endpoint(ASTRA_DB_ENDPOINT)
    _collection = database.get_collection("knowledge_base")
    logger.info("Connected to Astra DB collection 'knowledge_base'")
    return _collection


def check_connection() -> str:
    """Ping Astra DB. Returns 'connected' or 'error: ...'."""
    try:
        coll = _get_collection()
        coll.count_documents(filter={}, upper_bound=1000)
        return "connected"
    except Exception as exc:
        return f"error: {exc}"


async def search(
    query: str,
    limit: int = 5,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search using $vectorize (server-side embedding).

    Returns list of {doc_id, text, language, score, type}.
    """
    coll = _get_collection()

    filter_dict: dict[str, Any] = {}
    if language:
        filter_dict["language"] = language

    cursor = coll.find(
        filter=filter_dict,
        sort={"$vectorize": query},
        limit=limit,
        include_similarity=True,
    )

    results = []
    for doc in cursor:
        results.append({
            "doc_id": doc.get("_id", ""),
            "text": doc.get("text", doc.get("$vectorize", "")),
            "language": doc.get("language"),
            "score": doc.get("$similarity"),
            "type": doc.get("type", "knowledge_base"),
        })
    return results


async def ingest(
    doc_id: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Add or update a document in the knowledge base.

    Uses find_one_and_replace with upsert for idempotent writes.
    $vectorize triggers automatic server-side embedding.
    """
    coll = _get_collection()

    document: dict[str, Any] = {
        "_id": doc_id,
        "$vectorize": text[:MAX_VECTORIZE_CHARS],
        "text": text,
        "type": "knowledge_base",
    }

    if metadata:
        for key, value in metadata.items():
            if key not in ("_id", "$vectorize", "text"):
                document[key] = value

    try:
        coll.find_one_and_replace(
            filter={"_id": doc_id},
            replacement=document,
            upsert=True,
        )
        logger.info("Ingested document '%s'", doc_id)
        return True
    except Exception as exc:
        logger.error("Ingest failed for '%s': %s", doc_id, exc)
        return False
