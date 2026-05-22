"""Astra DB service — connect, search, ingest, update, delete documents.

Uses server-side NVIDIA NV-Embed-QA embeddings via $vectorize.
Supports multiple collections: knowledge_base, resolved_tickets.
"""

import logging
from typing import Any

from astrapy import Collection, DataAPIClient
from astrapy.info import CollectionDefinition

from app.config import ASTRA_DB_ENDPOINT, ASTRA_DB_TOKEN

logger = logging.getLogger(__name__)

MAX_VECTORIZE_CHARS = 2000

COLLECTIONS = ("knowledge_base", "resolved_tickets", "ticket_db")

_VECTORIZE_DEFINITION = (
    CollectionDefinition.builder()
    .set_vector_dimension(1024)
    .set_vector_metric("cosine")
    .set_vector_service("nvidia", "NV-Embed-QA")
    .build()
)

_collections: dict[str, Collection] = {}
_db = None


def _get_db():
    global _db
    if _db is None:
        client = DataAPIClient(ASTRA_DB_TOKEN)
        _db = client.get_database_by_api_endpoint(ASTRA_DB_ENDPOINT)
    return _db


def _get_collection(name: str) -> Collection:
    if name not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {name}. Must be one of {COLLECTIONS}")

    if name in _collections:
        return _collections[name]

    db = _get_db()

    existing_names = {c.name for c in db.list_collections()}

    if name in existing_names:
        coll = db.get_collection(name)
        logger.info("Connected to existing Astra DB collection '%s'", name)
    else:
        coll = db.create_collection(name, definition=_VECTORIZE_DEFINITION)
        logger.info("Created Astra DB collection '%s'", name)

    _collections[name] = coll
    return coll


def check_connection() -> str:
    try:
        coll = _get_collection("knowledge_base")
        coll.count_documents(filter={}, upper_bound=1000)
        return "connected"
    except Exception as exc:
        return f"error: {exc}"


async def search(collection: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    coll = _get_collection(collection)

    cursor = coll.find(
        sort={"$vectorize": query},
        limit=limit,
        include_similarity=True,
    )

    results = []
    for doc in cursor:
        result = {
            "doc_id": doc.get("_id", ""),
            "text": doc.get("text", doc.get("$vectorize", "")),
            "score": doc.get("$similarity"),
            "type": doc.get("type", collection),
        }
        # Include all metadata fields (skip internal Astra fields)
        skip = {"_id", "$vectorize", "$similarity", "$vector", "text", "type"}
        for key, value in doc.items():
            if key not in skip and value is not None:
                result[key] = value
        results.append(result)
    return results


async def ingest(
    collection: str,
    doc_id: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    coll = _get_collection(collection)

    document: dict[str, Any] = {
        "_id": doc_id,
        "$vectorize": text[:MAX_VECTORIZE_CHARS],
        "text": text,
        "type": collection,
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
        logger.info("Ingested document '%s' into '%s'", doc_id, collection)
        return True
    except Exception as exc:
        logger.error("Ingest failed for '%s' in '%s': %s", doc_id, collection, exc)
        return False


async def update(
    collection: str,
    doc_id: str,
    text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    coll = _get_collection(collection)

    update_fields: dict[str, Any] = {}

    if text is not None:
        update_fields["$vectorize"] = text[:MAX_VECTORIZE_CHARS]
        update_fields["text"] = text

    if metadata:
        for key, value in metadata.items():
            if key not in ("_id", "$vectorize", "text"):
                update_fields[key] = value

    if not update_fields:
        return False

    try:
        result = coll.find_one_and_update(
            filter={"_id": doc_id},
            update={"$set": update_fields},
        )
        if result is None:
            logger.warning("Document '%s' not found in '%s'", doc_id, collection)
            return False
        logger.info("Updated document '%s' in '%s'", doc_id, collection)
        return True
    except Exception as exc:
        logger.error("Update failed for '%s' in '%s': %s", doc_id, collection, exc)
        return False


async def delete_one(collection: str, doc_id: str) -> bool:
    coll = _get_collection(collection)
    try:
        result = coll.delete_one(filter={"_id": doc_id})
        deleted = result.deleted_count > 0
        if deleted:
            logger.info("Deleted document '%s' from '%s'", doc_id, collection)
        else:
            logger.warning("Document '%s' not found in '%s'", doc_id, collection)
        return deleted
    except Exception as exc:
        logger.error("Delete failed for '%s' in '%s': %s", doc_id, collection, exc)
        return False


async def delete_all(collection: str) -> int:
    coll = _get_collection(collection)
    try:
        result = coll.delete_many(filter={})
        logger.info("Cleared %d documents from '%s'", result.deleted_count, collection)
        return result.deleted_count
    except Exception as exc:
        logger.error("Clear failed for '%s': %s", collection, exc)
        return 0


async def count(collection: str) -> int:
    coll = _get_collection(collection)
    try:
        return coll.count_documents(filter={}, upper_bound=10000)
    except Exception as exc:
        logger.error("Count failed for '%s': %s", collection, exc)
        return 0
