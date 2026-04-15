"""RuagRAG — FastAPI tool backend for RUAG Feedback Management.

wxO handles orchestration and user-facing chat.
FastAPI is the tool layer: wxO calls these endpoints via OpenAPI.
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app import astra
from app.schemas import (
    CountResponse,
    DeleteResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    UpdateRequest,
    UpdateResponse,
)

app = FastAPI(
    title="RuagRAG Tool API",
    description="Tool endpoints for wxO agents. wxO calls these via OpenAPI during ReAct reasoning.",
    version="0.3.0",
)


# --- Health ---


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Check Astra DB connection status."""
    astra_status = astra.check_connection()

    return HealthResponse(
        status="ok" if astra_status == "connected" else "error",
        astra_db=astra_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# --- Knowledge Base ---


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


# --- Resolved Tickets ---


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
