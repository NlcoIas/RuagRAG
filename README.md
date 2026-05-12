# RuagRAG

**RUAG Feedback Management System** — An AI-powered support backend that uses IBM watsonx Orchestrate with IBM Granite LLMs to answer user questions by intelligently searching a knowledge base and resolved tickets database.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [IBM watsonx Orchestrate & Granite](#ibm-watsonx-orchestrate--granite)
- [DataStax Astra DB & Vector Search](#datastax-astra-db--vector-search)
- [API Reference](#api-reference)
- [Jira Integration](#jira-integration)
- [Project Structure](#project-structure)
- [Setup & Running](#setup--running)
- [Deployment](#deployment)
- [Configuration](#configuration)

---

## Overview

RuagRAG is a **FastAPI backend** that serves as the central hub for a RUAG feedback management system. It connects three things:

1. **A frontend** (or any HTTP client) that sends user questions
2. **IBM watsonx Orchestrate (wxO)** — an agentic AI platform that reasons about questions using **IBM Granite** LLMs
3. **DataStax Astra DB** — a vector database that stores company knowledge and past resolved tickets for semantic search (RAG)

The system implements **Retrieval-Augmented Generation (RAG)**: when a user asks a question, the AI agent retrieves relevant documents from the knowledge base, then generates an answer grounded in that context — reducing hallucination and providing accurate, source-backed responses.

---

## Architecture

```
┌──────────────┐
│   Frontend   │
│  (any client)│
└──────┬───────┘
       │  POST /api/chat
       ▼
┌──────────────────────────────────┐
│         FastAPI (Hub)            │
│         app/main.py              │
│                                  │
│  • /api/chat          (proxy)    │
│  • /api/rag/knowledge/* (CRUD)   │
│  • /api/rag/tickets/*   (CRUD)   │
│  • /api/health        (status)   │
└──────┬───────────┬───────────────┘
       │           │
       │           │  tool callbacks
       ▼           ▼
┌──────────────┐  ┌─────────────────────────┐
│ IBM watsonx  │  │   DataStax Astra DB     │
│ Orchestrate  │  │   (Vector Database)     │
│              │  │                         │
│ Granite LLM  │  │ ┌─────────────────────┐ │
│ Agent with   │──│►│  knowledge_base     │ │
│ tool-calling │  │ │  (domain docs)      │ │
│              │  │ └─────────────────────┘ │
│              │  │ ┌─────────────────────┐ │
│              │──│►│  resolved_tickets   │ │
│              │  │ │  (past solutions)   │ │
│              │  │ └─────────────────────┘ │
└──────────────┘  └─────────────────────────┘
```

**FastAPI is the hub** — both the frontend and wxO talk through it:

- **Frontend → FastAPI → wxO**: User messages are proxied to the wxO agent
- **wxO → FastAPI → Astra**: The agent calls back to FastAPI's search endpoints as tools during reasoning
- **FastAPI → Frontend**: The agent's response (with citations) is returned to the user

---

## How It Works

### Chat Flow (step by step)

```
1. User sends a question via POST /api/chat
       ↓
2. FastAPI obtains an IBM Cloud IAM token (cached for ~55 min)
       ↓
3. FastAPI submits the message to wxO's /v1/orchestrate/runs endpoint
       ↓
4. wxO's Granite agent reasons about the question
       ↓
5. Granite decides it needs context → calls FastAPI tools:
   • POST /api/rag/knowledge/search  → search domain docs
   • POST /api/rag/tickets/search    → search past solutions
       ↓
6. Astra DB performs vector similarity search using NVIDIA embeddings
       ↓
7. Search results flow back: Astra → FastAPI → wxO
       ↓
8. Granite formulates an answer grounded in the retrieved context
       ↓
9. FastAPI polls wxO until the run completes (up to 25 seconds)
       ↓
10. FastAPI returns the response with citations to the frontend:
    { "reply": "...", "thread_id": "...", "sources": [...] }
```

### Conversation Threading

Conversations are stateful via `thread_id`. The first message creates a new thread; subsequent messages with the same `thread_id` continue the conversation, giving the agent full conversation history for context.

---

## IBM watsonx Orchestrate & Granite

### What is watsonx Orchestrate?

[IBM watsonx Orchestrate (wxO)](https://www.ibm.com/products/watsonx-orchestrate) is an agentic AI platform that:

- Hosts **AI agents** powered by IBM's **Granite** LLM family
- Supports **tool-calling**: agents can invoke external APIs (like our search endpoints) during reasoning
- Manages **conversation threads** with full history
- Returns structured responses with **citations** back to the original sources

### What is IBM Granite?

[IBM Granite](https://www.ibm.com/granite) is IBM's family of enterprise-grade large language models. In this system, Granite:

- **Reasons** about user questions to determine what information is needed
- **Decides** which tools to call (knowledge base search, ticket search, or both)
- **Synthesizes** answers from retrieved documents
- **Cites** its sources so users can verify the information

Granite models are purpose-built for enterprise use cases with strong performance on RAG tasks, tool use, and multilingual support.

### Authentication

wxO uses IBM Cloud IAM for authentication:

1. An API key is exchanged for a bearer token via `https://iam.cloud.ibm.com/identity/token`
2. Tokens are cached in memory and refreshed 5 minutes before expiry (tokens last ~60 minutes)
3. On 401 errors, the token is automatically refreshed and the request retried

### wxO API Flow

```python
# 1. Submit a run
POST {WXO_URL}/instances/{instance_id}/v1/orchestrate/runs
{
    "message": {"role": "user", "content": "..."},
    "agent_id": "...",
    "environment_id": "...",
    "thread_id": "..."  # optional, for continuing conversations
}

# 2. Poll for completion
GET  {WXO_URL}/instances/{instance_id}/v1/orchestrate/runs/{run_id}
     ?thread_id={thread_id}

# 3. Response shape
{
    "status": "completed",
    "thread_id": "...",
    "result": {
        "data": {
            "message": {
                "content": [
                    {
                        "text": "The agent's answer...",
                        "citations": [
                            {"title": "...", "body": "..."}
                        ]
                    }
                ]
            }
        }
    }
}
```

---

## DataStax Astra DB & Vector Search

### What is Astra DB?

[DataStax Astra DB](https://www.datastax.com/products/datastax-astra) is a serverless vector database built on Apache Cassandra. It provides:

- **Vector storage and search** — stores document embeddings and performs similarity search
- **Server-side embeddings** — automatically generates embeddings using NVIDIA NV-Embed-QA (no local embedding model needed)
- **Serverless scaling** — no infrastructure to manage

### Collections

The system maintains two separate vector collections:

| Collection | Purpose | Example Content |
|---|---|---|
| `knowledge_base` | Company domain knowledge | Product documentation, FAQs, policies, procedures |
| `resolved_tickets` | Past support cases + solutions | "Error X occurred because of Y, fixed by doing Z" |

Separating these allows the Granite agent to search them independently and weight results differently based on the question type.

### Vector Configuration

- **Dimensions**: 1024
- **Similarity metric**: Cosine
- **Embedding model**: NVIDIA NV-Embed-QA (server-side, via Astra's `$vectorize`)
- **Max vectorized text**: 2,000 characters (first 2000 chars of each document are embedded; full text is stored separately)

### Document Structure

```json
{
    "_id": "doc-unique-id",
    "$vectorize": "First 2000 chars (auto-embedded by Astra)",
    "text": "Full document text (any length)",
    "type": "knowledge_base | resolved_tickets",
    "language": "en",
    "...": "any additional metadata fields"
}
```

### How Search Works

1. User query is sent to Astra's `find()` with `sort: {"$vectorize": query}`
2. Astra embeds the query server-side using NVIDIA NV-Embed-QA
3. Cosine similarity is computed against all document embeddings
4. Top N results are returned with similarity scores (0.0 to 1.0)

---

## API Reference

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Check Astra DB and wxO connection status |

Returns: `{ status: "ok" | "degraded" | "error", astra_db: "...", wxo: "...", timestamp: "..." }`

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a message to the Granite agent |

Request:
```json
{
    "message": "How do I reset my password?",
    "thread_id": null,
    "agent_id": null
}
```

Response:
```json
{
    "reply": "To reset your password, go to Settings > Security...",
    "thread_id": "thread_abc123",
    "sources": [
        {"title": "Password Reset Guide", "body": "..."}
    ]
}
```

- `thread_id`: `null` for new conversation, or pass previous `thread_id` to continue
- `agent_id`: `null` uses the default agent from config, or pass a specific agent UUID

### Knowledge Base

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/rag/knowledge/search` | Semantic search across knowledge base |
| `POST` | `/api/rag/knowledge/ingest` | Add or update a document |
| `GET` | `/api/rag/knowledge/count` | Count documents |
| `PUT` | `/api/rag/knowledge/{doc_id}` | Update a document's text/metadata |
| `DELETE` | `/api/rag/knowledge/{doc_id}` | Delete a specific document |
| `DELETE` | `/api/rag/knowledge/clear` | Delete all documents |

### Resolved Tickets

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/rag/tickets/search` | Semantic search across resolved tickets |
| `POST` | `/api/rag/tickets/ingest` | Add or update a ticket |
| `GET` | `/api/rag/tickets/count` | Count tickets |
| `PUT` | `/api/rag/tickets/{doc_id}` | Update a ticket's text/metadata |
| `DELETE` | `/api/rag/tickets/{doc_id}` | Delete a specific ticket |
| `DELETE` | `/api/rag/tickets/clear` | Delete all tickets |

### Jira Webhook

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/jira/webhook` | Receive Jira webhook events (issue created, resolved) |

Response:
```json
{
    "issue_key": "FEEDBACK-1",
    "action": "ai_response",
    "success": true,
    "detail": "AI response will be posted as internal comment"
}
```

Actions: `ai_response` (new ticket → Granite), `ingested` (resolved → Astra DB), `ignored` (unhandled event).

### Interactive Documentation

When running locally, Swagger UI is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Jira Integration

RuagRAG integrates with **Jira Service Management (JSM)** as a frontend and ticketing system. When enabled, tickets created in Jira are automatically processed by the Granite AI agent, and resolved tickets are ingested back into the knowledge base for future RAG.

### How It Works

```
1. Customer creates a ticket in Jira (via JSM portal or manually)
2. Jira fires a webhook → POST /api/jira/webhook
3. RuagRAG sends the question to Granite (via wxO)
4. Granite searches knowledge base + resolved tickets
5. AI response is posted as an internal comment on the Jira ticket
6. Agent reviews the AI suggestion, edits if needed, replies to customer
7. When the ticket is resolved → Q+A is auto-ingested into resolved_tickets
```

### Setup (Step by Step)

#### 1. Create a Jira Service Management Project

1. Go to [Jira Service Management Free](https://www.atlassian.com/software/jira/service-management/free) (3 agents free)
2. Create a site (e.g., `yourorg.atlassian.net`)
3. Create a **Service Management** project (e.g., key: `FEEDBACK`)

#### 2. Get an API Token

1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create a token named `RuagRAG Bot`
3. Copy it immediately

#### 3. Configure Environment Variables

Add to your `.env`:

```
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=FEEDBACK
```

All four must be set to enable the integration. If any are missing, Jira endpoints return 503.

#### 4. Register a Webhook in Jira

1. Go to **Jira Settings → System → WebHooks** (or use Jira Automation)
2. Create a webhook:
   - **URL**: `https://your-ruagrag-url/api/jira/webhook`
   - **Events**: `Issue created`, `Issue updated`
3. Scope it to your project (e.g., `FEEDBACK`)

**Alternative (simpler):** Use **Jira Automation** instead:
1. Go to **Project Settings → Automation**
2. Create rule: **When: Issue created → Then: Send web request**
   - URL: `https://your-ruagrag-url/api/jira/webhook`
   - Method: POST
   - Body: `{{issue}}`

#### 5. Expose RuagRAG to the Internet

Jira Cloud needs to reach your webhook. Options:
- **IBM Code Engine** — deploy and use the public URL
- **ngrok** — for local development: `ngrok http 8000`
- **Docker + reverse proxy** — if self-hosting

### Ticket Lifecycle

| Event | What RuagRAG Does |
|---|---|
| Ticket created | Sends ticket to wxO agent for triage → sets custom fields (department, urgency, confidence, triage level) → posts AI suggestion as **internal comment** → adds `ai-triaged` label |
| Ticket resolved | Extracts Q+A pair → ingests into `resolved_tickets` collection for future RAG |
| Other events | Ignored (returns 200 with `action: "ignored"`) |

### Self-Improving Knowledge Base

Every resolved ticket makes the system smarter:
1. Customer asks "How do I reset VPN?"
2. Agent resolves with the solution
3. RuagRAG ingests: `Question: How do I reset VPN? Resolution: Go to Settings > Network > Reset VPN...`
4. Next time someone asks about VPN, Granite finds this resolved ticket via semantic search

---

## Project Structure

```
RuagRAG/
├── app/
│   ├── __init__.py        # Module init
│   ├── main.py            # FastAPI app — 15 endpoints
│   ├── config.py          # Fail-fast env var loading (+ optional Jira)
│   ├── schemas.py         # Pydantic request/response models
│   ├── astra.py           # Astra DB vector service (search, ingest, CRUD)
│   ├── wxo.py             # watsonx Orchestrate client (IAM auth, chat, polling)
│   ├── jira.py            # Jira REST API client (comments, labels, webhook parsing)
│   └── triage.py          # AI triage engine (sends ticket to wxO agent for classification)
├── Dockerfile             # Production image (Python 3.12-slim, non-root)
├── docker-compose.yml     # Local dev stack
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
├── .env                   # Local credentials (gitignored)
├── .gitignore
└── .dockerignore
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Loads all environment variables at startup. Crashes immediately if any are missing. |
| `schemas.py` | Pydantic models for all request/response payloads. Provides automatic validation. |
| `astra.py` | All Astra DB operations: connection pooling, collection management, search, ingest, update, delete. Uses lazy-loaded global connections. |
| `wxo.py` | All wxO communication: IAM token management, chat submission, async polling, response parsing with citation extraction. |
| `jira.py` | Jira REST API client: post comments (internal/public), add labels, set custom fields, parse webhooks, extract ADF text. |
| `triage.py` | AI triage engine: sends ticket to wxO agent, agent searches both collections via tools, returns structured classification (department, urgency, confidence, triage level, suggested response). |
| `main.py` | FastAPI application with 15 endpoints. Routes requests to `astra.py`, `wxo.py`, `jira.py`, and `triage.py`. |

---

## Setup & Running

### Prerequisites

- Python 3.12+
- An IBM Cloud account with watsonx Orchestrate access
- A DataStax Astra DB instance
- An IBM Cloud API key

### Local Development

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd RuagRAG

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials (see Configuration section)

# 5. Run the development server
uvicorn app.main:app --reload

# 6. Open the API docs
# http://localhost:8000/docs
```

### Docker (local)

```bash
# Build and run with docker-compose
docker-compose up -d

# API available at http://localhost:8085
# (maps host 8085 → container 8080)
```

---

## Deployment

### Docker Image

The Dockerfile is optimized for production:

- **Base**: `python:3.12-slim` (minimal image)
- **Security**: Runs as non-root `appuser`
- **Layer caching**: Dependencies installed before code copy
- **No secrets**: `.env`, `.git`, and docs excluded via `.dockerignore`
- **Unbuffered output**: Logs appear immediately in log viewers

```bash
# Build
docker build -t ruagrag:latest .

# Run
docker run -p 8080:8080 \
  -e ASTRA_DB_ENDPOINT=... \
  -e ASTRA_DB_TOKEN=... \
  -e IBM_CLOUD_API_KEY=... \
  -e WXO_URL=... \
  -e WXO_AGENT_ID=... \
  -e WXO_ENV_ID=... \
  -e WXO_INSTANCE_ID=... \
  ruagrag:latest
```

### IBM Code Engine

The Dockerfile is ready for IBM Code Engine deployment. Code Engine injects the `PORT` environment variable automatically (defaults to 8080).

---

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|---|---|---|
| `ASTRA_DB_ENDPOINT` | Astra DB API endpoint | `https://<db-id>.apps.astra.datastax.com` |
| `ASTRA_DB_TOKEN` | Astra DB application token | `AstraCS:...` |
| `IBM_CLOUD_API_KEY` | IBM Cloud IAM API key | `(your key)` |
| `WXO_URL` | watsonx Orchestrate API base URL | `https://api.eu-de.watson-orchestrate.cloud.ibm.com` |
| `WXO_AGENT_ID` | UUID of the wxO agent to use | `(uuid)` |
| `WXO_ENV_ID` | UUID of the wxO environment | `(uuid)` |
| `WXO_INSTANCE_ID` | UUID of the wxO instance | `(uuid)` |

All variables are **required**. The application will crash at startup with a clear error message if any are missing.

### Optional Environment Variables (Jira)

| Variable | Description | Example |
|---|---|---|
| `JIRA_BASE_URL` | Jira Cloud base URL | `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | Email for API authentication | `bot@yourorg.com` |
| `JIRA_API_TOKEN` | Jira API token | `(your token)` |
| `JIRA_PROJECT_KEY` | Project key for tickets | `FEEDBACK` |

All four must be set to enable Jira integration. If any are missing, the webhook endpoint returns 503.

### Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.12 | Web framework |
| `uvicorn[standard]` | 0.34.2 | ASGI server |
| `astrapy` | 2.2.1 | DataStax Astra DB SDK |
| `httpx` | 0.28.1 | Async HTTP client (for wxO API calls) |
| `python-dotenv` | 1.1.0 | Load `.env` files |
