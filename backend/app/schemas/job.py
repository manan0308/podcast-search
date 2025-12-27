from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class JobResponse(BaseModel):
    id: UUID
    batch_id: UUID | None
    episode_id: UUID
    provider: str
    provider_job_id: str | None
    status: str
    progress: int
    current_step: str | None
    error_message: str | None
    error_code: str | None
    retry_count: int
    cost_cents: int | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Computed
    duration_seconds: int | None = None

    class Config:
        from_attributes = True


class JobDetailResponse(JobResponse):
    episode_title: str
    episode_youtube_id: str
    batch_name: str | None = None

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


class ActivityLogResponse(BaseModel):
    id: int
    batch_id: UUID | None
    job_id: UUID | None
    episode_id: UUID | None
    level: str
    message: str
    metadata: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityLogListResponse(BaseModel):
    logs: list[ActivityLogResponse]
    total: int
