"""Request and response models for the API."""

from typing import Any

from pydantic import BaseModel


# --- Health ---


class HealthResponse(BaseModel):
    status: str
    astra_db: str
    wxo: str
    timestamp: str


# --- Chat (frontend → FastAPI → wxO) ---


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # None = new conversation
    agent_id: str | None = None   # None = default agent from config


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    sources: list[dict[str, Any]]


# --- RAG ---


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class SearchResponse(BaseModel):
    results: list[dict[str, Any]]
    count: int


class IngestRequest(BaseModel):
    doc_id: str
    text: str
    metadata: dict[str, Any] | None = None


class IngestResponse(BaseModel):
    success: bool
    doc_id: str


class UpdateRequest(BaseModel):
    text: str | None = None
    metadata: dict[str, Any] | None = None


class UpdateResponse(BaseModel):
    success: bool
    doc_id: str


class CountResponse(BaseModel):
    collection: str
    count: int


class DeleteResponse(BaseModel):
    success: bool
    doc_id: str | None = None
    collection: str | None = None
    deleted_count: int | None = None


# --- Jira Webhook ---


class JiraWebhookResponse(BaseModel):
    issue_key: str
    action: str  # "ai_response" | "ingested" | "ignored"
    success: bool
    detail: str | None = None
