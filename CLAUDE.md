# RuagRAG — Project Context

## What This Is

RUAG Feedback Management System — a FastAPI backend that connects a frontend, IBM watsonx Orchestrate (with Granite LLMs), and DataStax Astra DB for AI-powered support ticket resolution via RAG.

## Architecture

FastAPI is the **central hub**:
- Frontend → FastAPI → wxO (chat proxy)
- wxO → FastAPI → Astra DB (tool callbacks for search)
- FastAPI exposes 12 endpoints: health, chat, and CRUD for two vector collections

## Tech Stack

- **Python 3.12**, FastAPI, Uvicorn, httpx, astrapy, python-dotenv
- **IBM watsonx Orchestrate** — agentic AI with IBM Granite LLMs
- **DataStax Astra DB** — vector DB with NVIDIA NV-Embed-QA embeddings (1024-dim, cosine)
- **Docker** — production image (python:3.12-slim, non-root, IBM Code Engine ready)

## Key Files

- `app/main.py` — FastAPI routes (12 endpoints)
- `app/wxo.py` — wxO client (IAM auth, async polling, response parsing)
- `app/astra.py` — Astra DB service (search, ingest, update, delete)
- `app/schemas.py` — Pydantic request/response models
- `app/config.py` — Fail-fast env var loading

## Collections

Two Astra DB vector collections:
- `knowledge_base` — domain docs, FAQs, policies
- `resolved_tickets` — past support cases and their solutions

## Environment Variables (all required)

```
ASTRA_DB_ENDPOINT, ASTRA_DB_TOKEN
IBM_CLOUD_API_KEY
WXO_URL, WXO_AGENT_ID, WXO_ENV_ID, WXO_INSTANCE_ID
```

## Running

```bash
# Local
uvicorn app.main:app --reload

# Docker
docker-compose up -d  # port 8085
```

## Conventions

- Async-first (FastAPI, httpx)
- Fully typed with Python type hints
- Separation of concerns: config / schemas / services / routes
- Server-side embeddings via Astra $vectorize (no local embedding model)
- IAM tokens cached 55 min, auto-refresh on 401

## Next Steps

- Jira Service Management integration (webhook endpoint + Jira API client)
- Auto-ingest resolved tickets from Jira on resolution
- Frontend / dashboard (or Jira as frontend)
