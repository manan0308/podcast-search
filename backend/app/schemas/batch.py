from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Literal, Optional


class EpisodeData(BaseModel):
    """Episode data from YouTube fetch for batch creation."""

    youtube_id: str
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    published_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class ChannelData(BaseModel):
    """Channel data from YouTube fetch for batch creation."""

    name: str
    youtube_channel_id: str
    youtube_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None


class BatchCreate(BaseModel):
    """Create a batch - either from existing channel/episodes or from YouTube data."""

    # Option 1: Existing channel
    channel_id: Optional[UUID] = None
    episode_ids: Optional[list[UUID]] = None

    # Option 2: New channel from YouTube fetch
    channel_data: Optional[ChannelData] = None
    episodes_data: Optional[list[EpisodeData]] = None

    # Common fields
    provider: str = Field(
        description="Provider name: assemblyai, deepgram, faster-whisper, modal-cloud"
    )
    concurrency: int = Field(default=10, ge=1, le=100)
    speakers: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class BatchStartRequest(BaseModel):
    """Request to start a batch that's in pending state."""

    pass


class BatchResponse(BaseModel):
    id: UUID
    channel_id: UUID | None
    name: str | None
    provider: str
    concurrency: int
    config: dict
    total_episodes: int
    completed_episodes: int
    failed_episodes: int
    estimated_cost_cents: int | None
    actual_cost_cents: int
    status: str
    progress_percent: float
    started_at: datetime | None
    paused_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobSummary(BaseModel):
    id: UUID
    episode_id: UUID
    episode_title: str
    status: str
    progress: int
    current_step: str | None
    error_message: str | None
    cost_cents: int | None
    started_at: datetime | None
    completed_at: datetime | None


class BatchDetailResponse(BatchResponse):
    jobs: list[JobSummary] = []
    channel_name: str | None = None

    class Config:
        from_attributes = True


class BatchListResponse(BaseModel):
    batches: list[BatchResponse]
    total: int
