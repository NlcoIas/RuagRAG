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
