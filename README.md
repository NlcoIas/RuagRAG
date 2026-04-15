# RuagRAG

RUAG Feedback Management System — IBM watsonx Agentic AI

## Setup

1. Copy `.env.example` to `.env` and fill in credentials
2. Install: `pip install -r requirements.txt`
3. Run: `uvicorn app.main:app --reload`
4. Open: http://localhost:8000/docs

## Endpoints

- `GET /api/health` — Check Astra DB + wxO connections
- `POST /api/chat` — Talk to wxO agent
- `POST /api/rag/knowledge/search` — Semantic search in knowledge base
- `POST /api/rag/knowledge/ingest` — Add a document to knowledge base
