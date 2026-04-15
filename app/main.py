"""RuagRAG — FastAPI backend for RUAG Feedback Management."""

from datetime import datetime, timezone

from fastapi import FastAPI

from app import astra, wxo
from app.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
)

app = FastAPI(
    title="RuagRAG API",
    description="RUAG Feedback Management — IBM watsonx Agentic AI",
    version="0.1.0",
)


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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Send a message to the wxO agent."""
    result = await wxo.chat(
        message=body.message,
        thread_id=body.thread_id,
        agent_id=body.agent_id,
    )
    return ChatResponse(**result)


@app.post(
    "/api/rag/knowledge/search",
    response_model=SearchResponse,
    operation_id="search_knowledge_base",
    description="Semantic search in the company knowledge base.",
)
async def rag_search(body: SearchRequest):
    """Search the knowledge base using semantic similarity."""
    results = await astra.search(query=body.query, limit=body.limit)
    return SearchResponse(results=results, count=len(results))


@app.post(
    "/api/rag/knowledge/ingest",
    response_model=IngestResponse,
    operation_id="ingest_knowledge_document",
    description="Add or update a document in the knowledge base.",
)
async def rag_ingest(body: IngestRequest):
    """Add a document to the knowledge base."""
    success = await astra.ingest(
        doc_id=body.doc_id,
        text=body.text,
        metadata=body.metadata,
    )
    return IngestResponse(success=success, doc_id=body.doc_id)
