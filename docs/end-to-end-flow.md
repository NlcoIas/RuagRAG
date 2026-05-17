# RuagRAG — End-to-End Technical Flow

## Architecture Overview

```
┌─────────────┐     webhook      ┌──────────────────┐    IAM + chat    ┌─────────────────┐
│   Customer   │ ──────────────► │     FastAPI       │ ──────────────► │  IBM watsonx     │
│  (Jira JSM)  │                 │  (Code Engine)    │ ◄────────────── │  Orchestrate     │
└─────────────┘                  │                   │   tool calls    │  (Granite LLM)   │
                                 │  nsc-testing.     │                 └─────────────────┘
      ▲                          │  27cltkbcyac0.    │
      │                          │  eu-de.codeengine │
      │  fields + comment        │  .appdomain.cloud │
      └──────────────────────────│                   │
                                 │                   │──────────────► ┌─────────────────┐
┌─────────────┐  invoke()        │                   │ ◄──────────── │  DataStax        │
│ Forge Panel │ ────────────────►│  /api/refine      │  vector search │  Astra DB        │
│ (Jira UI)   │ ◄────────────── │                   │               │  (NVIDIA embed)  │
└─────────────┘  refined text    └──────────────────┘               └─────────────────┘
```

---

## Phase 1: Ticket Intake

### 1.1 Customer Creates Ticket

Customer submits via JSM portal at `ruagdesk.atlassian.net`. Jira creates issue (e.g. `SUP-24`).

### 1.2 Jira Webhook Fires

Jira's built-in webhook (configured via REST API) sends:

```
POST https://nsc-testing.27cltkbcyac0.eu-de.codeengine.appdomain.cloud/api/jira/webhook
```

**Payload (Jira V2 webhook format):**
```json
{
  "webhookEvent": "jira:issue_created",
  "issue": {
    "key": "SUP-24",
    "fields": {
      "summary": "VPN not connecting after update",
      "description": {
        "version": 1,
        "type": "doc",
        "content": [
          {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Since the last Windows update..."}]
          }
        ]
      }
    }
  }
}
```

### 1.3 FastAPI Receives and Routes

**File:** `app/main.py:317` → `jira_webhook()`

1. Extracts `issue_key`, `summary`, `description` (ADF → plain text via `jira.extract_issue_text()`)
2. Detects event type: `jira:issue_created` → spawns background task `_handle_new_ticket()`

---

## Phase 2: AI Triage

### 2.1 Build Triage Prompt

**File:** `app/triage.py:58` → `_build_triage_prompt(question)`

Constructs a structured prompt that instructs Granite to search both collections and return classification:

```
Triage this support ticket. You MUST:

1. Search the knowledge base for relevant documents
2. Search resolved tickets for similar past cases
3. Classify the ticket based on what you find

TICKET:
VPN not connecting after update
Since the last Windows update my VPN keeps disconnecting...

After searching, respond with EXACTLY this JSON format (no other text):
{
  "department": "IT|HR|Facilities|Finance|Legal|General",
  "urgency": "Highest|High|Medium|Low|Lowest",
  "confidence": "High|Medium|Low",
  "triage_level": "L1 - Self-Service|L2 - Agent|L3 - Expert",
  "suggested_response": "Your detailed response based on the search results...",
  "kb_score": 0.85,
  "kb_match": "Brief summary of best knowledge base match",
  "ticket_score": 0.72,
  "ticket_match": "Brief summary of best resolved ticket match"
}

CONFIDENCE RULES:
- If KB score > 0.7 AND Ticket score > 0.7 → "High" (documented + solved before)
- If KB score > 0.7 OR Ticket score > 0.7 → "Medium" (partially matched)
- If both scores < 0.7 → "Low" (new/unknown issue)
```

### 2.2 Authenticate with IBM Cloud

**File:** `app/wxo.py:31` → `_get_iam_token()`

```
POST https://iam.cloud.ibm.com/identity/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=<IBM_CLOUD_API_KEY>
```

**Response:**
```json
{"access_token": "eyJ...", "expiration": 1779045600}
```

Token cached in memory for 55 minutes. Auto-refreshes on 401.

### 2.3 Submit Run to wxO

**File:** `app/wxo.py:126` → `chat(message=prompt)`

```
POST https://api.eu-de.watson-orchestrate.cloud.ibm.com
     /instances/ed36a570-326b-4ac2-86dd-e0877ae1abbc/v1/orchestrate/runs

Authorization: Bearer eyJ...
Content-Type: application/json

{
  "message": {"role": "user", "content": "<triage prompt>"},
  "agent_id": "76831f79-36d4-4820-8593-1329ec74c533",
  "environment_id": "188a8594-1dad-4874-a5a8-aa642756120c"
}
```

**Response:**
```json
{"run_id": "run_abc123", "thread_id": "thread_xyz", "status": "in_progress"}
```

---

## Phase 3: Granite Agent Reasoning + RAG

### 3.1 Agent Decides to Search

The Granite LLM inside wxO reads the triage prompt, reasons it needs context, and makes **tool callbacks** to FastAPI:

### 3.2 Tool Call: Search Knowledge Base

wxO calls back to FastAPI:

```
POST https://nsc-testing.27cltkbcyac0.eu-de.codeengine.appdomain.cloud
     /api/rag/knowledge/search

{"query": "VPN not connecting after Windows update", "limit": 5}
```

**File:** `app/main.py:93` → `kb_search()` → `app/astra.py` → Astra DB

### 3.3 Tool Call: Search Resolved Tickets

```
POST https://nsc-testing.27cltkbcyac0.eu-de.codeengine.appdomain.cloud
     /api/rag/tickets/search

{"query": "VPN not connecting after Windows update", "limit": 5}
```

**File:** `app/main.py:176` → `tickets_search()` → `app/astra.py` → Astra DB

### 3.4 Astra DB Vector Search

**File:** `app/astra.py` → `search(collection, query, limit)`

```python
collection.find(
    sort={"$vectorize": query},     # Astra embeds query server-side
    limit=limit,
    include_similarity=True,
)
```

| Setting | Value |
|---------|-------|
| Embedding model | NVIDIA NV-Embed-QA (server-side via `$vectorize`) |
| Dimensions | 1024 |
| Similarity metric | Cosine |
| Max vectorized text | 2,000 characters |

**Two separate collections:**

| Collection | Purpose | Example content |
|------------|---------|-----------------|
| `knowledge_base` | Company docs, FAQs, policies | "To reset VPN, go to Settings > Network..." |
| `resolved_tickets` | Past Q+A pairs from resolved Jira tickets | "Q: VPN disconnecting → A: Reset VPN config in Settings" |

**Returns:**
```json
[
  {"text": "VPN Reset Guide: Go to Settings > Network...", "similarity": 0.87, "metadata": {...}},
  {"text": "Network troubleshooting FAQ...", "similarity": 0.63, "metadata": {...}}
]
```

### 3.5 FastAPI Polls for Completion

**File:** `app/wxo.py:169` — polls every 1 second, up to 25 times:

```
GET https://api.eu-de.watson-orchestrate.cloud.ibm.com
    /instances/ed36a570-.../v1/orchestrate/runs/run_abc123
    ?thread_id=thread_xyz

Authorization: Bearer eyJ...
```

Until `status: "completed"`.

---

## Phase 4: Granite Returns Structured Result

### 4.1 wxO Response Shape

```json
{
  "status": "completed",
  "thread_id": "thread_xyz",
  "result": {
    "data": {
      "message": {
        "content": [
          {
            "text": "<JSON string — the triage result>",
            "citations": [
              {"title": "VPN Reset Guide", "body": "..."}
            ]
          }
        ]
      }
    }
  }
}
```

### 4.2 Triage Result (parsed JSON)

**File:** `app/triage.py:90` → `_parse_triage_response(reply)`

```json
{
  "department": "IT",
  "urgency": "High",
  "confidence": "High",
  "triage_level": "L1 - Self-Service",
  "suggested_response": "To fix your VPN after the Windows update, go to Settings > Network > VPN and click 'Reset Configuration'. If the issue persists, restart your machine and reconnect.",
  "kb_score": 0.87,
  "kb_match": "VPN Reset Guide",
  "ticket_score": 0.72,
  "ticket_match": "SUP-15: VPN disconnecting after patch"
}
```

Mapped to Python dataclass:

```python
@dataclass
class TriageResult:
    department: str       # IT, HR, Facilities, Finance, Legal, General
    urgency: str          # Highest, High, Medium, Low, Lowest
    confidence: str       # High, Medium, Low
    triage_level: str     # L1 - Self-Service, L2 - Agent, L3 - Expert
    suggested_response: str
    kb_score: float       # 0.0–1.0 cosine similarity
    kb_match: str         # best KB article title
    ticket_score: float   # 0.0–1.0 cosine similarity
    ticket_match: str     # best resolved ticket summary
```

---

## Phase 5: Write Results Back to Jira

### 5.1 Set Custom Fields

**File:** `app/jira.py:182` → `set_triage_fields()`

```
PUT https://ruagdesk.atlassian.net/rest/api/3/issue/SUP-24
Authorization: Basic <base64(email:token)>
Content-Type: application/json

{
  "fields": {
    "priority": {"id": "2"},
    "customfield_10055": {"id": "10032"},
    "customfield_10056": {"id": "10035"},
    "customfield_10057": {"id": "10041"},
    "customfield_10058": 0.87,
    "customfield_10059": 0.72,
    "customfield_10060": "VPN Reset Guide",
    "customfield_10061": "SUP-15: VPN disconnecting after patch",
    "customfield_10062": {
      "version": 1,
      "type": "doc",
      "content": [
        {
          "type": "paragraph",
          "content": [{"type": "text", "text": "To fix your VPN..."}]
        }
      ]
    }
  }
}
```

**Custom field ID mapping:**

| Field ID | Name | Type | Values |
|----------|------|------|--------|
| `customfield_10055` | AI Confidence | Select | High (10032), Medium (10033), Low (10034) |
| `customfield_10056` | Department | Select | IT (10035), HR (10036), Facilities (10037), Finance (10038), Legal (10039), General (10040) |
| `customfield_10057` | Triage Level | Select | L1 - Self-Service (10041), L2 - Agent (10042), L3 - Expert (10043) |
| `customfield_10058` | KB Similarity | Number | 0.0–1.0 |
| `customfield_10059` | Ticket Similarity | Number | 0.0–1.0 |
| `customfield_10060` | KB Best Match | Text | Max 250 chars |
| `customfield_10061` | Ticket Best Match | Text | Max 250 chars |
| `customfield_10062` | AI Suggested Response | ADF Textarea | Max 5000 chars |

### 5.2 Post Internal Comment

**File:** `app/jira.py:48` → `add_comment(issue_key, comment, internal=True)`

```
POST https://ruagdesk.atlassian.net/rest/api/3/issue/SUP-24/comment

{
  "body": {
    "version": 1,
    "type": "doc",
    "content": [
      {
        "type": "paragraph",
        "content": [{
          "type": "text",
          "text": "🤖 AI Triage Complete\n\nDepartment: IT\nConfidence: High | Level: L1\nKB Score: 0.87 | Ticket Score: 0.72\n\nSuggested Response:\nTo fix your VPN..."
        }]
      }
    ]
  },
  "properties": [
    {"key": "sd.public.comment", "value": {"internal": true}}
  ]
}
```

### 5.3 Add Label

**File:** `app/jira.py:98` → `add_label(issue_key, "ai-triaged")`

```
PUT https://ruagdesk.atlassian.net/rest/api/3/issue/SUP-24

{"update": {"labels": [{"add": "ai-triaged"}]}}
```

---

## Phase 6: Agent Reviews via Forge Panel

### 6.1 Panel Loads

Forge app (Atlassian-hosted) renders in Jira's right sidebar as `jira:issueContext`.

**File:** `forge/src/resolver.js` → `getInitialData()`

Reads from Jira REST API:
```
GET /rest/api/3/issue/SUP-24?fields=customfield_10055,customfield_10056,
    customfield_10057,customfield_10058,customfield_10059,customfield_10062
```

Extracts suggestion text (ADF → plain text), metadata, and loads version history from Forge Storage.

### 6.2 Agent Refines (optional)

Agent types feedback (e.g. "make it friendlier") → clicks **Refine**.

```
Forge UI → invoke("refine", {currentText, feedback})
  → Forge resolver → POST https://nsc-testing.../api/refine
      Authorization: Bearer <FORGE_API_KEY>
      {"current_text": "To fix your VPN...", "feedback": "make it friendlier", "issue_key": "SUP-24"}
    → FastAPI → wxo.chat(rewrite prompt)
    → Granite rewrites text
    → Returns {"refined_text": "Hey! To get your VPN back on track...", "success": true}
  → Forge UI adds new version tab, updates text
```

**Rewrite prompt** (simple, no RAG):
```
Rewrite the following customer support response.
Apply this feedback: make it friendlier

CURRENT RESPONSE:
To fix your VPN after the Windows update, go to Settings > Network...

Return ONLY the rewritten response text. No explanations, no formatting, no preamble.
```

### 6.3 Agent Sends to Customer

Agent clicks **Send to Customer**.

```
Forge UI → invoke("send", {text})
  → Forge resolver → POST /rest/api/3/issue/SUP-24/comment (via Forge's Jira API)
      Body: ADF document with the final text
      Posted as: public comment (customer sees it)
  → Forge UI shows "Comment posted to SUP-24"
```

---

## Phase 7: Resolution → Self-Improving Loop

### 7.1 Ticket Resolved

Agent resolves the ticket. Jira webhook fires again:

```json
{
  "webhookEvent": "jira:issue_updated",
  "changelog": {
    "items": [{"field": "resolution", "to": "Done"}]
  },
  "issue": {"key": "SUP-24", "fields": {"summary": "...", "description": "..."}}
}
```

### 7.2 Ingest Q+A for Future RAG

**File:** `app/main.py:287` → `_handle_resolution()`

1. Fetches issue + comments from Jira
2. Extracts Q+A pair:
   - **Question** = summary + description
   - **Answer** = last non-AI comment (the human resolution)
3. Ingests into Astra DB:

```python
astra.ingest(
    collection="resolved_tickets",
    doc_id="jira-SUP-24",
    text="Question: VPN not connecting after update\n\nResolution: Go to Settings > Network > VPN, click Reset Configuration...",
    metadata={"source": "jira", "issue_key": "SUP-24", "summary": "VPN not connecting"}
)
```

Next time someone asks about VPN issues, this resolved ticket appears in the vector search results → better answers over time.

---

## Future: wxO Agent Does Everything

Currently FastAPI orchestrates the triage logic. In a future architecture, a wxO agent flow could do it all:

```
Current:  Jira → FastAPI (orchestrates triage) → wxO (reasons) ←→ FastAPI (tools) → Jira
Future:   Jira → FastAPI (just forwards)       → wxO (orchestrates + reasons + writes) → Jira
```

**The wxO agent would need these registered tools:**

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `search_knowledge_base` | `POST /api/rag/knowledge/search` | Search company docs |
| `search_resolved_tickets` | `POST /api/rag/tickets/search` | Search past cases |
| `set_triage_fields` | `PUT /api/jira/fields/{issue_key}` (new) | Write classification to Jira |
| `add_comment` | `POST /api/jira/comment/{issue_key}` (new) | Post reply to ticket |
| `fetch_policy` | `POST /api/rag/policy/fetch` | Look up specific policies |

**FastAPI changes:**
- Remove `triage.py` (wxO handles reasoning + classification)
- Keep all `/api/rag/*` endpoints as tool backends
- Add thin Jira write endpoints so wxO can update tickets directly
- Webhook just forwards raw ticket text to `wxo.chat()`

**wxO agent's system prompt** would contain the triage instructions (department rules, confidence rules, JSON format) instead of `_build_triage_prompt()` in Python.
