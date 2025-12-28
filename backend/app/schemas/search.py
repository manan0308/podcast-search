from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    speaker: str | None = None
    channel_id: UUID | None = None
    channel_slug: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    filters: SearchFilters | None = None
    limit: int = Field(default=10, ge=1, le=50)
    include_context: bool = True
    context_utterances: int = Field(default=3, ge=0, le=10)

    # Hybrid search options
    use_hybrid: bool = Field(
        default=True, description="Use hybrid search (semantic + keyword BM25)"
    )
    use_reranking: bool = Field(
        default=True, description="Re-rank results with cross-encoder"
    )
    semantic_weight: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Weight for semantic search (0-1)"
    )
    keyword_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight for keyword/BM25 search (0-1)"
    )


class ContextUtterance(BaseModel):
    speaker: str
    text: str
    start_ms: int
    end_ms: int


class SearchResult(BaseModel):
    chunk_id: UUID
    episode_id: UUID
    channel_id: UUID
    episode_title: str
    episode_url: str | None
    episode_thumbnail: str | None
    channel_name: str
    channel_slug: str
    speaker: str | None
    speakers: list[str]
    text: str
    timestamp: str
    timestamp_ms: int
    published_at: datetime | None
    score: float
    context_before: list[ContextUtterance] = []
    context_after: list[ContextUtterance] = []


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str
    processing_time_ms: int
