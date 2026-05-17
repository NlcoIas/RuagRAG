# Forge AI Reply Assistant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Jira Forge issue panel that lets agents review, refine (via AI), and send AI-generated reply suggestions — plus a new FastAPI `/api/refine` endpoint that rewrites text based on agent feedback.

**Architecture:** FastAPI gets one new endpoint (`/api/refine`) that takes text + feedback and sends a rewrite prompt to wxO. A new Forge Custom UI app (React + `@forge/bridge`) displays the AI suggestion from `customfield_10062`, supports inline editing, AI refinement with version history, and one-click send to customer. The Forge resolver bridges the UI to FastAPI and Jira's REST API.

**Tech Stack:** Python/FastAPI (backend), Node.js/@forge/resolver (Forge backend), React/@forge/bridge/Vite (Forge frontend), Forge Storage API (version persistence)

**Spec:** `docs/superpowers/specs/2026-05-17-forge-ai-reply-assistant-design.md`

---

## File Structure

### Backend (modify existing)

| File | Action | Responsibility |
|------|--------|----------------|
| `app/config.py` | Modify | Add optional `FORGE_API_KEY` env var |
| `app/schemas.py` | Modify | Add `RefineRequest`, `RefineResponse` models |
| `app/main.py` | Modify | Add `POST /api/refine` endpoint + auth dependency |
| `tests/test_refine.py` | Create | Tests for the refine endpoint |

### Forge App (new)

| File | Action | Responsibility |
|------|--------|----------------|
| `forge/manifest.yml` | Create | Forge app declaration: issue panel, resolver, permissions, external fetch |
| `forge/package.json` | Create | Resolver dependencies: `@forge/resolver`, `@forge/api` |
| `forge/src/resolver.js` | Create | Three resolver functions: `getInitialData`, `refine`, `send` |
| `forge/frontend/package.json` | Create | Frontend dependencies: `react`, `react-dom`, `@forge/bridge`, `vite` |
| `forge/frontend/index.html` | Create | HTML entry point for Vite |
| `forge/frontend/vite.config.js` | Create | Vite build config (output to `../static`) |
| `forge/frontend/src/main.jsx` | Create | React entry point |
| `forge/frontend/src/App.jsx` | Create | Main panel component: editable text, version tabs, refine, send |
| `forge/frontend/src/styles.css` | Create | Jira Atlassian Design System dark theme |

### Config

| File | Action | Responsibility |
|------|--------|----------------|
| `.gitignore` | Modify | Add `forge/node_modules/`, `forge/frontend/node_modules/`, `forge/static/`, `.superpowers/` |

---

## Task 1: Backend — Config + Schemas

**Files:**
- Modify: `app/config.py:31-37`
- Modify: `app/schemas.py:83-87`

- [ ] **Step 1: Add `FORGE_API_KEY` to config**

In `app/config.py`, add after the `JIRA_ENABLED` line (line 37):

```python
# Forge app authentication (optional — open if not set)
FORGE_API_KEY = os.getenv("FORGE_API_KEY")
```

- [ ] **Step 2: Add `RefineRequest` and `RefineResponse` schemas**

In `app/schemas.py`, add after the `JiraWebhookResponse` class (after line 87):

```python
# --- Refine (Forge → FastAPI → wxO rewrite) ---


class RefineRequest(BaseModel):
    current_text: str
    feedback: str
    issue_key: str | None = None  # optional, for logging


class RefineResponse(BaseModel):
    refined_text: str
    success: bool
```

- [ ] **Step 3: Commit**

```bash
git add app/config.py app/schemas.py
git commit -m "feat: add FORGE_API_KEY config + refine schemas"
```

---

## Task 2: Backend — `/api/refine` Endpoint + Tests

**Files:**
- Modify: `app/main.py:1-31` (imports), append new section at end
- Create: `tests/__init__.py`
- Create: `tests/test_refine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty file).

Create `tests/test_refine.py`:

```python
"""Tests for the /api/refine endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create a test client with FORGE_API_KEY unset (open access)."""
    with patch("app.config.FORGE_API_KEY", None):
        from app.main import app
        return TestClient(app)


@pytest.fixture()
def client_with_key():
    """Create a test client with FORGE_API_KEY set."""
    with patch("app.config.FORGE_API_KEY", "test-secret-key"):
        from app.main import app
        return TestClient(app)


class TestRefineEndpoint:
    """Tests for POST /api/refine."""

    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_returns_refined_text(self, mock_chat, client):
        mock_chat.return_value = {
            "reply": "Hey! Here is your friendlier response.",
            "thread_id": "t1",
            "sources": [],
        }

        resp = client.post("/api/refine", json={
            "current_text": "Reset your VPN in Settings.",
            "feedback": "make it friendlier",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["refined_text"] == "Hey! Here is your friendlier response."

    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_sends_rewrite_prompt_to_wxo(self, mock_chat, client):
        mock_chat.return_value = {
            "reply": "rewritten",
            "thread_id": "t1",
            "sources": [],
        }

        client.post("/api/refine", json={
            "current_text": "Original text.",
            "feedback": "shorter",
            "issue_key": "FEEDBACK-42",
        })

        prompt = mock_chat.call_args[1]["message"]
        assert "Original text." in prompt
        assert "shorter" in prompt

    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_handles_wxo_error(self, mock_chat, client):
        mock_chat.return_value = {
            "reply": "",
            "thread_id": "",
            "sources": [],
        }

        resp = client.post("/api/refine", json={
            "current_text": "Some text.",
            "feedback": "improve it",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestRefineAuth:
    """Tests for FORGE_API_KEY authentication."""

    @patch("app.config.FORGE_API_KEY", "test-secret-key")
    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_rejects_missing_key(self, mock_chat):
        from app.main import app
        client = TestClient(app)

        resp = client.post("/api/refine", json={
            "current_text": "text",
            "feedback": "feedback",
        })

        assert resp.status_code == 401

    @patch("app.config.FORGE_API_KEY", "test-secret-key")
    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_rejects_wrong_key(self, mock_chat):
        from app.main import app
        client = TestClient(app)

        resp = client.post(
            "/api/refine",
            json={"current_text": "text", "feedback": "feedback"},
            headers={"Authorization": "Bearer wrong-key"},
        )

        assert resp.status_code == 401

    @patch("app.config.FORGE_API_KEY", "test-secret-key")
    @patch("app.wxo.chat", new_callable=AsyncMock)
    def test_refine_accepts_correct_key(self, mock_chat):
        mock_chat.return_value = {"reply": "ok", "thread_id": "t1", "sources": []}
        from app.main import app
        client = TestClient(app)

        resp = client.post(
            "/api/refine",
            json={"current_text": "text", "feedback": "feedback"},
            headers={"Authorization": "Bearer test-secret-key"},
        )

        assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/nsc/claude/RuagRAG && pip install pytest httpx 2>/dev/null && python -m pytest tests/test_refine.py -v`

Expected: FAIL — `/api/refine` endpoint doesn't exist yet.

- [ ] **Step 3: Implement the `/api/refine` endpoint**

In `app/main.py`, add to the imports section (around line 13):

```python
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
```

Add the new schema imports (around line 28, inside the existing import block):

```python
    RefineRequest,
    RefineResponse,
```

Add after the existing imports, before the `app = FastAPI(...)` line:

```python
from app.config import FORGE_API_KEY, JIRA_ENABLED
```

(Replace the existing `from app.config import JIRA_ENABLED` line.)

Add at the end of `app/main.py`, after the Jira webhook section:

```python
# --- Refine (Forge → FastAPI → wxO rewrite) ---


async def _verify_forge_key(request: Request) -> None:
    """Validate the Forge API key if one is configured."""
    if not FORGE_API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {FORGE_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.post("/api/refine", response_model=RefineResponse, dependencies=[Depends(_verify_forge_key)])
async def refine(body: RefineRequest):
    """Rewrite an AI-generated response based on agent feedback.

    Called by the Forge issue panel. Sends a simple rewrite prompt to wxO
    (no RAG, no tool-calling — just text transformation).
    """
    prompt = (
        f"Rewrite the following customer support response.\n"
        f"Apply this feedback: {body.feedback}\n\n"
        f"CURRENT RESPONSE:\n{body.current_text}\n\n"
        f"Return ONLY the rewritten response text. No explanations, no formatting, no preamble."
    )

    if body.issue_key:
        logger.info("Refine request for %s: %s", body.issue_key, body.feedback[:100])

    result = await wxo.chat(message=prompt)
    reply = result.get("reply", "").strip()

    if not reply:
        return RefineResponse(refined_text=body.current_text, success=False)

    return RefineResponse(refined_text=reply, success=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_refine.py -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/__init__.py tests/test_refine.py
git commit -m "feat: add POST /api/refine endpoint with auth"
```

---

## Task 3: Forge — Scaffold Project

**Files:**
- Create: `forge/manifest.yml`
- Create: `forge/package.json`
- Create: `forge/src/resolver.js` (stub)
- Create: `forge/frontend/package.json`
- Create: `forge/frontend/index.html`
- Create: `forge/frontend/vite.config.js`
- Create: `forge/frontend/src/main.jsx` (stub)
- Modify: `.gitignore`

- [ ] **Step 1: Create `forge/manifest.yml`**

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
      resource: static
permissions:
  scopes:
    - read:jira-work
    - write:jira-work
    - storage:app
  external:
    fetch:
      backend:
        - '${RUAGRAG_API_URL}'
app:
  runtime:
    name: nodejs18.x
  id: ari:cloud:ecosystem::app/to-be-assigned
```

Note: `app.id` gets replaced when you run `forge register`.

- [ ] **Step 2: Create `forge/package.json`**

```json
{
  "name": "forge-ai-reply-assistant",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "build:frontend": "cd frontend && npm run build",
    "postinstall": "cd frontend && npm install"
  },
  "dependencies": {
    "@forge/api": "^4.0.0",
    "@forge/resolver": "^1.6.0"
  }
}
```

- [ ] **Step 3: Create `forge/frontend/package.json`**

```json
{
  "name": "ai-reply-assistant-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@forge/bridge": "^3.0.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 4: Create `forge/frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI Reply Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `forge/frontend/vite.config.js`**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
});
```

- [ ] **Step 6: Create stub `forge/frontend/src/main.jsx`**

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
```

- [ ] **Step 7: Create stub `forge/frontend/src/App.jsx`**

```jsx
import React from "react";

function App() {
  return <div className="panel-body"><p>Loading...</p></div>;
}

export default App;
```

- [ ] **Step 8: Create empty `forge/frontend/src/styles.css`**

```css
/* Jira Atlassian Design System theme — populated in Task 5 */
```

- [ ] **Step 9: Create stub `forge/src/resolver.js`**

```js
import Resolver from "@forge/resolver";

const resolver = new Resolver();

resolver.define("getInitialData", async ({ payload, context }) => {
  return { suggestion: "", metadata: {}, versions: [] };
});

resolver.define("refine", async ({ payload }) => {
  return { refined_text: "", success: false };
});

resolver.define("send", async ({ payload }) => {
  return { success: false };
});

export const handler = resolver.getDefinitions();
```

- [ ] **Step 10: Update `.gitignore`**

Append to `.gitignore`:

```
# Forge
forge/node_modules/
forge/frontend/node_modules/
forge/static/

# Superpowers
.superpowers/
```

- [ ] **Step 11: Verify frontend builds**

```bash
cd /home/nsc/claude/RuagRAG/forge/frontend && npm install && npm run build
```

Expected: Build succeeds, `forge/static/` directory created with `index.html` + JS/CSS assets.

- [ ] **Step 12: Commit**

```bash
cd /home/nsc/claude/RuagRAG
git add forge/ .gitignore
git commit -m "feat: scaffold Forge AI Reply Assistant app"
```

---

## Task 4: Forge — Resolver Functions

**Files:**
- Modify: `forge/src/resolver.js`

- [ ] **Step 1: Implement the full resolver**

Replace `forge/src/resolver.js` with:

```js
import Resolver from "@forge/resolver";
import api, { route, storage, fetch } from "@forge/api";

const resolver = new Resolver();

/**
 * Extract plain text from an Atlassian Document Format (ADF) node.
 */
function adfToText(adf) {
  if (!adf || !adf.content) return "";
  let text = "";
  for (const block of adf.content) {
    if (block.type === "paragraph" && block.content) {
      for (const inline of block.content) {
        if (inline.type === "text") {
          text += inline.text || "";
        }
      }
      text += "\n";
    } else if (block.type === "text") {
      text += block.text || "";
    } else if (block.content) {
      text += adfToText(block);
    }
  }
  return text.trim();
}

/**
 * Read the value of a select custom field (returns the option's name string).
 */
function selectValue(field) {
  if (!field) return "";
  if (typeof field === "string") return field;
  return field.value || field.name || "";
}

/**
 * Load initial data for the panel: AI suggestion + metadata + version history.
 */
resolver.define("getInitialData", async ({ payload, context }) => {
  const issueKey = context.extension.issue.key;

  // Fetch issue fields
  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}?fields=customfield_10055,customfield_10056,customfield_10057,customfield_10058,customfield_10059,customfield_10062`
  );
  const issue = await resp.json();
  const fields = issue.fields || {};

  // Extract suggestion text from ADF
  const suggestionAdf = fields.customfield_10062;
  const suggestionText = suggestionAdf ? adfToText(suggestionAdf) : "";

  // Extract metadata
  const metadata = {
    confidence: selectValue(fields.customfield_10055),
    department: selectValue(fields.customfield_10056),
    triageLevel: selectValue(fields.customfield_10057),
    kbScore: fields.customfield_10058 || 0,
    ticketScore: fields.customfield_10059 || 0,
  };

  // Load version history from Forge Storage
  const storageKey = `versions-${issueKey}`;
  const stored = await storage.get(storageKey);
  let versions = stored || [];

  // If no versions yet, initialize with the original suggestion
  if (versions.length === 0 && suggestionText) {
    versions = [{ text: suggestionText, feedback: null, timestamp: Date.now() }];
    await storage.set(storageKey, versions);
  }

  return { issueKey, suggestion: suggestionText, metadata, versions };
});

/**
 * Refine the suggestion text via the FastAPI /api/refine endpoint.
 */
resolver.define("refine", async ({ payload, context }) => {
  const { currentText, feedback } = payload;
  const issueKey = context.extension.issue.key;

  const apiUrl = process.env.RUAGRAG_API_URL;
  const apiKey = process.env.FORGE_API_KEY;

  const headers = { "Content-Type": "application/json" };
  if (apiKey) {
    headers["Authorization"] = `Bearer ${apiKey}`;
  }

  const resp = await fetch(`${apiUrl}/api/refine`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      current_text: currentText,
      feedback: feedback,
      issue_key: issueKey,
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    return { refined_text: currentText, success: false, error: errText };
  }

  const data = await resp.json();

  if (data.success) {
    // Save new version to Forge Storage
    const storageKey = `versions-${issueKey}`;
    const stored = (await storage.get(storageKey)) || [];
    stored.push({
      text: data.refined_text,
      feedback: feedback,
      timestamp: Date.now(),
    });
    await storage.set(storageKey, stored);
  }

  return data;
});

/**
 * Send the final text as a public customer comment on the Jira issue.
 */
resolver.define("send", async ({ payload, context }) => {
  const { text } = payload;
  const issueKey = context.extension.issue.key;

  const adfBody = {
    version: 1,
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [{ type: "text", text: text }],
      },
    ],
  };

  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}/comment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: adfBody }),
    }
  );

  if (resp.ok) {
    return { success: true };
  }

  const errText = await resp.text();
  return { success: false, error: errText };
});

export const handler = resolver.getDefinitions();
```

- [ ] **Step 2: Commit**

```bash
cd /home/nsc/claude/RuagRAG
git add forge/src/resolver.js
git commit -m "feat: implement Forge resolver — getInitialData, refine, send"
```

---

## Task 5: Forge — Custom UI (React + Jira Theme)

**Files:**
- Modify: `forge/frontend/src/App.jsx`
- Modify: `forge/frontend/src/styles.css`

- [ ] **Step 1: Implement `forge/frontend/src/styles.css`**

```css
:root {
  --bg-page: #1D2125;
  --bg-panel: #22272B;
  --bg-input: #1D2125;
  --border: #2C333A;
  --border-focus: #579DFF;
  --text-primary: #B6C2CF;
  --text-secondary: #596773;
  --text-muted: #8C9BAB;
  --blue: #0C66E4;
  --blue-light: #579DFF;
  --green: #4BCE97;
  --green-bg: #1C3329;
  --yellow: #E2B203;
  --yellow-bg: #332E1B;
  --blue-bg: #1C2B41;
  --neutral-bg: #2C333A;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
  background: var(--bg-page);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
}

.panel-body {
  padding: 16px;
}

/* Loading / empty states */
.loading, .empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: var(--text-secondary);
  font-size: 13px;
}

/* Section labels */
.label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

/* Version tabs */
.versions {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.version-tab {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 3px;
  cursor: pointer;
  border: none;
  background: var(--neutral-bg);
  color: var(--text-muted);
  font-family: inherit;
  transition: background 0.15s;
}

.version-tab:hover {
  background: #38414A;
}

.version-tab.active {
  background: var(--blue);
  color: #fff;
}

/* Suggestion textarea */
.suggestion-box {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  line-height: 1.6;
  min-height: 100px;
  resize: vertical;
  margin-bottom: 4px;
  transition: border-color 0.15s;
}

.suggestion-box:focus {
  outline: none;
  border-color: var(--border-focus);
}

.edit-hint {
  font-size: 11px;
  color: var(--text-secondary);
  text-align: right;
  margin-bottom: 10px;
}

/* Metadata badges */
.badges {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 3px;
}

.badge-green { background: var(--green-bg); color: var(--green); }
.badge-blue { background: var(--blue-bg); color: var(--blue-light); }
.badge-neutral { background: var(--neutral-bg); color: var(--text-muted); }
.badge-yellow { background: var(--yellow-bg); color: var(--yellow); }

/* Refinement log */
.refine-log {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  padding: 8px 10px;
  background: var(--bg-input);
  border-radius: 4px;
  border-left: 3px solid var(--blue-light);
}

.refine-log-entry {
  margin-bottom: 3px;
}

.refine-log-entry:last-child {
  margin-bottom: 0;
}

.refine-log-entry b {
  color: var(--text-muted);
}

/* Feedback input */
.feedback-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
  color: var(--text-primary);
  font-size: 12px;
  font-family: inherit;
  margin-bottom: 10px;
  transition: border-color 0.15s;
}

.feedback-input:focus {
  outline: none;
  border-color: var(--border-focus);
}

.feedback-input::placeholder {
  color: var(--text-secondary);
}

/* Buttons */
.actions {
  display: flex;
  gap: 8px;
}

.btn {
  flex: 1;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  border: none;
  transition: background 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-refine {
  background: var(--neutral-bg);
  color: var(--blue-light);
}

.btn-refine:hover:not(:disabled) {
  background: #38414A;
}

.btn-send {
  background: var(--blue);
  color: #fff;
}

.btn-send:hover:not(:disabled) {
  background: #0055CC;
}

/* Success banner */
.success-banner {
  background: var(--green-bg);
  color: var(--green);
  padding: 10px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  margin-top: 10px;
}

/* Error text */
.error-text {
  color: #EF5C48;
  font-size: 11px;
  margin-top: 4px;
}
```

- [ ] **Step 2: Implement `forge/frontend/src/App.jsx`**

```jsx
import React, { useState, useEffect } from "react";
import { invoke } from "@forge/bridge";

function App() {
  const [loading, setLoading] = useState(true);
  const [issueKey, setIssueKey] = useState("");
  const [versions, setVersions] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [editedText, setEditedText] = useState("");
  const [metadata, setMetadata] = useState({});
  const [feedback, setFeedback] = useState("");
  const [refining, setRefining] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    invoke("getInitialData").then((data) => {
      setIssueKey(data.issueKey || "");
      setMetadata(data.metadata || {});
      const v = data.versions || [];
      setVersions(v);
      if (v.length > 0) {
        setCurrentIdx(v.length - 1);
        setEditedText(v[v.length - 1].text);
      }
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="panel-body loading">Loading suggestion...</div>;
  }

  if (versions.length === 0) {
    return (
      <div className="panel-body empty">
        No AI suggestion available for this ticket.
      </div>
    );
  }

  const handleVersionClick = (idx) => {
    setCurrentIdx(idx);
    setEditedText(versions[idx].text);
    setError("");
  };

  const handleRefine = async () => {
    if (!feedback.trim()) return;
    setRefining(true);
    setError("");

    const result = await invoke("refine", {
      currentText: editedText,
      feedback: feedback.trim(),
    });

    if (result.success) {
      const newVersion = {
        text: result.refined_text,
        feedback: feedback.trim(),
        timestamp: Date.now(),
      };
      const updated = [...versions, newVersion];
      setVersions(updated);
      setCurrentIdx(updated.length - 1);
      setEditedText(result.refined_text);
      setFeedback("");
    } else {
      setError(result.error || "Refinement failed. Try again.");
    }

    setRefining(false);
  };

  const handleSend = async () => {
    setError("");
    const result = await invoke("send", { text: editedText });
    if (result.success) {
      setSent(true);
    } else {
      setError(result.error || "Failed to send comment.");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleRefine();
    }
  };

  // Build refinement log (skip v1 which has no feedback)
  const refinements = versions
    .map((v, i) => ({ ...v, idx: i }))
    .filter((v) => v.feedback);

  return (
    <div className="panel-body">
      {/* Version tabs */}
      <span className="label">Version</span>
      <div className="versions">
        {versions.map((v, i) => (
          <button
            key={i}
            className={`version-tab ${i === currentIdx ? "active" : ""}`}
            onClick={() => handleVersionClick(i)}
          >
            {i === 0 ? "v1 original" : `v${i + 1}${v.feedback ? ` "${v.feedback}"` : ""}`}
          </button>
        ))}
      </div>

      {/* Editable suggestion */}
      <span className="label">Suggested reply</span>
      <textarea
        className="suggestion-box"
        value={editedText}
        onChange={(e) => setEditedText(e.target.value)}
        disabled={sent}
      />
      <div className="edit-hint">Click to edit directly</div>

      {/* Metadata badges */}
      <div className="badges">
        {metadata.confidence && (
          <span className={`badge ${metadata.confidence === "High" ? "badge-green" : metadata.confidence === "Medium" ? "badge-yellow" : "badge-neutral"}`}>
            {metadata.confidence} confidence
          </span>
        )}
        {metadata.department && (
          <span className="badge badge-blue">{metadata.department}</span>
        )}
        {metadata.triageLevel && (
          <span className="badge badge-neutral">{metadata.triageLevel}</span>
        )}
        {metadata.kbScore > 0 && (
          <span className="badge badge-yellow">
            KB: {Number(metadata.kbScore).toFixed(2)}
          </span>
        )}
      </div>

      {/* Refinement log */}
      {refinements.length > 0 && (
        <>
          <span className="label">Refinement history</span>
          <div className="refine-log">
            {refinements.map((v) => (
              <div key={v.idx} className="refine-log-entry">
                <b>v{v.idx + 1}:</b> &ldquo;{v.feedback}&rdquo;
              </div>
            ))}
          </div>
        </>
      )}

      {/* Feedback + actions */}
      {!sent && (
        <>
          <span className="label">Refine with AI</span>
          <input
            className="feedback-input"
            placeholder="e.g. 'make it more direct', 'add a greeting'"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={refining}
          />
          <div className="actions">
            <button
              className="btn btn-refine"
              onClick={handleRefine}
              disabled={refining || !feedback.trim()}
            >
              {refining ? "Refining..." : "Refine"}
            </button>
            <button className="btn btn-send" onClick={handleSend}>
              Send to Customer
            </button>
          </div>
        </>
      )}

      {sent && (
        <div className="success-banner">
          Comment posted to {issueKey}
        </div>
      )}

      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Build the frontend**

```bash
cd /home/nsc/claude/RuagRAG/forge/frontend && npm run build
```

Expected: Build succeeds. `forge/static/` contains `index.html` + hashed JS/CSS assets.

- [ ] **Step 4: Commit**

```bash
cd /home/nsc/claude/RuagRAG
git add forge/frontend/src/App.jsx forge/frontend/src/styles.css
git commit -m "feat: Forge Custom UI — editable text, version history, refine + send"
```

---

## Task 6: Finalize — Gitignore, Docs, Verification

**Files:**
- Modify: `.gitignore`
- Verify: all backend tests pass
- Verify: frontend builds clean

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/nsc/claude/RuagRAG && python -m pytest tests/ -v
```

Expected: All 6 tests pass.

- [ ] **Step 2: Verify frontend builds**

```bash
cd /home/nsc/claude/RuagRAG/forge/frontend && npm run build
```

Expected: Clean build, no warnings.

- [ ] **Step 3: Final commit**

```bash
cd /home/nsc/claude/RuagRAG
git add -A
git commit -m "chore: finalize Forge AI Reply Assistant scaffold"
```

---

## Deployment Checklist (manual — not automated)

Once the code is committed, the user needs to:

1. **Sign up** at `developer.atlassian.com` (use existing Atlassian/Jira account)
2. **Install Forge CLI**: `npm install -g @forge/cli`
3. **Login**: `forge login`
4. **Register the app**: `cd forge && forge register`
5. **Set environment variables**:
   ```bash
   forge variables set RUAGRAG_API_URL https://your-fastapi-url
   forge variables set --encrypt FORGE_API_KEY your-secret-key
   ```
6. **Build frontend**: `cd frontend && npm run build && cd ..`
7. **Deploy**: `forge deploy`
8. **Install on Jira site**: `forge install --site yourorg.atlassian.net`
9. **Set `FORGE_API_KEY`** in FastAPI's `.env` to match the value from step 5
10. **Test**: Create a ticket in Jira, wait for triage, open the ticket — panel should appear
