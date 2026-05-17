# Forge AI Reply Assistant — Design Spec

## Overview

A Jira Forge issue panel that lets support agents review, refine, and send AI-generated reply suggestions directly from the ticket view. Combines editable text, AI-powered refinement via natural language feedback, and version history.

## Problem

Today, when the triage pipeline generates a `suggested_response`, it's written to a custom field (`customfield_10062`) and posted as an internal comment. The agent must manually copy the suggestion, paste it into a reply, and edit it. There's no way to ask the AI to adjust tone/style, and no history of refinements.

## Solution

A Forge Custom UI issue panel ("AI Reply Assistant") that:

1. Reads the AI suggestion from `customfield_10062` and displays it as editable text
2. Lets the agent type natural language feedback (e.g. "make it friendlier") and click Refine — the text is rewritten by the AI
3. Tracks version history (v1, v2, v3...) so the agent can revert to any previous version
4. Posts the final text as a public JSM comment via "Send to Customer"

## Architecture

```
Agent opens ticket in Jira
  → Forge panel loads
  → Reads customfield_10062 (AI suggestion) via Jira REST API
  → Displays editable text + metadata badges

Agent clicks "Refine"
  → Forge resolver calls POST {RUAGRAG_API_URL}/api/refine
    → FastAPI sends rewrite prompt to wxO (simple text rewrite, no RAG)
    → Returns refined text
  → Forge UI adds new version, updates displayed text

Agent clicks "Send to Customer"
  → Forge resolver calls Jira REST API: add public comment (ADF format)
  → UI shows confirmation
```

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `/api/refine` endpoint | `app/main.py` | Accepts current text + feedback, sends rewrite prompt to wxO, returns refined text |
| `RefineRequest` / `RefineResponse` | `app/schemas.py` | Pydantic models for the refine endpoint |
| Auth middleware | `app/main.py` | Validates `FORGE_API_KEY` on `/api/refine` |
| Forge issue panel | `forge/src/index.jsx` | React Custom UI — editable text, version tabs, feedback input, refine + send buttons |
| Forge resolver | `forge/src/resolver.js` | Backend functions that call FastAPI and Jira REST API |
| Forge manifest | `forge/manifest.yml` | App declaration: issue panel module, permissions, env vars |

### What is NOT changed

- `app/wxo.py` — unchanged; `/api/refine` calls `wxo.chat()` with a rewrite prompt
- `app/triage.py` — unchanged; still fills `customfield_10062` on new tickets
- `app/jira.py` — unchanged; Forge handles its own Jira API calls
- All existing endpoints — unchanged

## Backend: `/api/refine` Endpoint

### Request

```
POST /api/refine
Authorization: Bearer {FORGE_API_KEY}

{
  "current_text": "To fix your VPN, go to Settings > Network...",
  "feedback": "make it friendlier",
  "issue_key": "FEEDBACK-42"  // optional, for logging
}
```

### Response

```json
{
  "refined_text": "Hey! To get your VPN back on track...",
  "success": true
}
```

### Rewrite prompt sent to wxO

```
Rewrite the following customer support response.
Apply this feedback: {feedback}

CURRENT RESPONSE:
{current_text}

Return ONLY the rewritten response text. No explanations, no formatting, no preamble.
```

This is a simple `wxo.chat()` call — no tool-calling, no RAG. The wxO agent receives a standalone rewrite instruction. Backlog: route through the full triage pipeline for context-aware refinement.

### Auth

- New optional env var: `FORGE_API_KEY`
- If set, `/api/refine` requires `Authorization: Bearer {key}` header
- If not set, endpoint is open (for local dev)
- Validated with a simple dependency/middleware check, not a full auth framework

### Config changes

`app/config.py` — add:

```python
FORGE_API_KEY = os.getenv("FORGE_API_KEY")  # optional
```

## Forge App

### Technology

- **Custom UI** (not UI Kit) — full control over HTML/CSS/React to match the Jira dark theme
- **@forge/bridge** — communication between Custom UI and resolver
- **@forge/api** — Jira REST API calls from the resolver
- **Forge Storage API** — per-issue version history persistence

### Manifest (`forge/manifest.yml`)

```yaml
modules:
  jira:issuePanel:
    - key: ai-reply-assistant
      title: AI Reply Assistant
      resource: main
      resolver:
        function: resolver
  function:
    - key: resolver
      handler: src/resolver.handler
  consumer:
    - key: main
      resource: static/index.html
permissions:
  scopes:
    - read:jira-work
    - write:jira-work
    - storage:app
  external:
    fetch:
      backend:
        - '{RUAGRAG_API_URL}'
app:
  runtime:
    name: nodejs18.x
  id: (assigned on forge register)
```

### UI Component (`forge/src/index.jsx`)

React app with these states:

- `versions[]` — array of `{text, feedback, timestamp}`, loaded from Forge Storage on mount
- `currentVersion` — index into versions array
- `editedText` — current text in the editable area (may differ from version text if manually edited)
- `feedback` — current feedback input value
- `loading` — true while refine is in progress
- `sent` — true after successful send

**On mount:**
1. Read `customfield_10062` from the Jira issue via resolver
2. Load version history from Forge Storage (`storage.get('versions-{issueKey}')`)
3. If no versions exist, initialize with v1 = the custom field text
4. Display current version in editable area

**On Refine click:**
1. Call resolver `refine` function with `{currentText, feedback}`
2. Resolver calls `POST {RUAGRAG_API_URL}/api/refine`
3. On success: push new version to `versions[]`, save to Forge Storage, switch to new version
4. Clear feedback input

**On version tab click:**
1. Switch `currentVersion` to selected index
2. Update `editedText` to that version's text

**On Send to Customer click:**
1. Call resolver `send` function with `{text, issueKey}`
2. Resolver calls Jira REST API to add public comment (ADF format)
3. Show confirmation, disable send button

### Resolver Functions (`forge/src/resolver.js`)

Three functions:

**`getInitialData(issueKey)`**
- Calls Jira REST API: `GET /rest/api/3/issue/{issueKey}?fields=customfield_10062,customfield_10055,customfield_10056,customfield_10057,customfield_10058,customfield_10059`
- Extracts suggestion text (from ADF), confidence, department, triage level, KB score, ticket score
- Loads version history from Forge Storage
- Returns all data to the UI

**`refine(currentText, feedback, issueKey)`**
- Calls `POST {RUAGRAG_API_URL}/api/refine` with `{current_text, feedback, issue_key}`
- Sends `Authorization: Bearer {FORGE_API_KEY}` header
- Saves updated version history to Forge Storage
- Returns refined text

**`send(text, issueKey)`**
- Calls Jira REST API: `POST /rest/api/3/issue/{issueKey}/comment`
- Body is ADF format (same structure as `jira.py:add_comment`)
- Posts as public comment (no `sd.public.comment` internal property)
- Returns success/failure

### Styling

Matches Jira's Atlassian Design System dark theme:

- Backgrounds: `#1D2125` (page), `#22272B` (panel), `#2C333A` (borders)
- Text: `#B6C2CF` (primary), `#596773` (secondary)
- Atlassian blue: `#0C66E4` (buttons), `#579DFF` (accents)
- Badge colors: green (`#4BCE97`), blue (`#579DFF`), yellow (`#E2B203`), neutral (`#8C9BAB`)
- Font: system font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto...`)
- Border radius: 4px (inputs, badges), 8px (panel)

Mockup saved at `.superpowers/brainstorm/` in the project.

### Forge Environment Variables

Set during `forge variables set`:

| Variable | Description | Example |
|----------|-------------|---------|
| `RUAGRAG_API_URL` | FastAPI backend URL | `https://ruagrag.xxx.ce.appdomain.cloud` |
| `FORGE_API_KEY` | Shared secret for `/api/refine` auth | `(random string)` |

## Deployment Prerequisites

1. **Atlassian Developer account** — sign up at `developer.atlassian.com` (free, instant)
2. **Forge CLI** — `npm install -g @forge/cli && forge login`
3. **Register the app** — `cd forge && forge register`
4. **Set env vars** — `forge variables set RUAGRAG_API_URL https://... && forge variables set --encrypt FORGE_API_KEY ...`
5. **Deploy** — `forge deploy && forge install --site yourorg.atlassian.net`
6. **FastAPI** must be publicly reachable (Code Engine, ngrok for dev)

## Backlog

- **Context-aware refinement**: Route refine through full wxO pipeline with RAG tool access instead of simple rewrite
- **Auto-send for high confidence**: Toggle to automatically post as public comment when confidence is High
- **Agent impersonation**: Use `act:jira-user` scope so comments appear from the agent, not the app
- **Refinement analytics**: Track how often agents refine, what feedback they give, which departments need most refinement
