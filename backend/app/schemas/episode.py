from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class UtteranceResponse(BaseModel):
    id: UUID
    speaker: str
    speaker_raw: str | None
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None
    timestamp: str

    class Config:
        from_attributes = True


class EpisodeBase(BaseModel):
    youtube_id: str
    title: str
    description: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None


class EpisodeCreate(EpisodeBase):
    channel_id: UUID


class EpisodeBulkCreate(BaseModel):
    """Create multiple episodes at once."""

    channel_id: UUID
    episodes: list[EpisodeBase]


class EpisodeResponse(BaseModel):
    id: UUID
    channel_id: UUID
    youtube_id: str
    title: str
    description: str | None
    url: str | None
    thumbnail_url: str | None
    published_at: datetime | None
    duration_seconds: int | None
    status: str
    word_count: int | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None

    class Config:
        from_attributes = True


class EpisodeListResponse(BaseModel):
    episodes: list[EpisodeResponse]
    total: int
    page: int
    page_size: int


class EpisodeDetailResponse(EpisodeResponse):
    utterances: list[UtteranceResponse] = []
    channel_name: str | None = None
    channel_slug: str | None = None

    class Config:
        from_attributes = True
