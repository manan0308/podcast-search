from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl


class ChannelBase(BaseModel):
    name: str
    description: str | None = None
    youtube_url: str | None = None
    speakers: list[str] = Field(default_factory=list)
    default_unknown_speaker_label: str = "Guest"


class ChannelCreate(ChannelBase):
    youtube_channel_id: str | None = None
    thumbnail_url: str | None = None


class ChannelUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    speakers: list[str] | None = None
    default_unknown_speaker_label: str | None = None


class ChannelResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    youtube_channel_id: str | None
    youtube_url: str | None
    thumbnail_url: str | None
    speakers: list[str]
    default_unknown_speaker_label: str
    episode_count: int
    transcribed_count: int
    total_duration_seconds: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChannelListResponse(BaseModel):
    channels: list[ChannelResponse]
    total: int


class EpisodePreview(BaseModel):
    id: UUID
    youtube_id: str
    title: str
    duration_seconds: int | None
    published_at: datetime | None
    thumbnail_url: str | None
    selected: bool = True

    class Config:
        from_attributes = True


class ChannelFetchRequest(BaseModel):
    youtube_url: str


class ChannelFetchResponse(BaseModel):
    channel_id: UUID | None = None
    name: str
    youtube_channel_id: str
    thumbnail_url: str | None
    description: str | None
    episodes: list[EpisodePreview]
    total_episodes: int
    is_new: bool = True
