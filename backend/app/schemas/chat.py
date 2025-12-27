from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ChatFilters(BaseModel):
    speaker: str | None = None
    channel_id: UUID | None = None
    channel_slug: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    filters: ChatFilters | None = None
    max_context_chunks: int = Field(default=10, ge=1, le=20)


class Citation(BaseModel):
    episode_id: UUID
    episode_title: str
    episode_url: str | None
    channel_name: str
    channel_slug: str
    speaker: str | None
    text: str
    timestamp: str
    timestamp_ms: int
    published_at: datetime | None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conversation_id: UUID
    search_results_used: int
    processing_time_ms: int


class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    citations: list[Citation] = []
    created_at: datetime


class ConversationResponse(BaseModel):
    id: UUID
    messages: list[ConversationMessage]
    created_at: datetime
