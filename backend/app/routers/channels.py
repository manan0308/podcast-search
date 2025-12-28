import re
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from slugify import slugify
from loguru import logger

from app.dependencies import DB, AdminAuth
from app.models import Channel, Episode
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelListResponse,
    ChannelFetchRequest,
    ChannelFetchResponse,
    EpisodePreview,
)
from app.services.youtube import YouTubeService


# YouTube URL validation patterns
YOUTUBE_CHANNEL_PATTERNS = [
    r"^https?://(?:www\.)?youtube\.com/@[\w\.\-]+/?$",
    r"^https?://(?:www\.)?youtube\.com/channel/UC[\w\-]+/?$",
    r"^https?://(?:www\.)?youtube\.com/c/[\w\.\-]+/?$",
    r"^https?://(?:www\.)?youtube\.com/user/[\w\.\-]+/?$",
]

YOUTUBE_VIDEO_PATTERNS = [
    r"^https?://(?:www\.)?youtube\.com/watch\?v=([\w\-]+)",
    r"^https?://youtu\.be/([\w\-]+)",
    r"^https?://(?:www\.)?youtube\.com/embed/([\w\-]+)",
    r"^https?://(?:www\.)?youtube\.com/v/([\w\-]+)",
]


def validate_youtube_url(url: str) -> bool:
    """Validate that URL is a valid YouTube channel URL."""
    for pattern in YOUTUBE_CHANNEL_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False


def extract_video_id(url: str) -> str | None:
    """Extract video ID from YouTube video URL."""
    for pattern in YOUTUBE_VIDEO_PATTERNS:
        match = re.match(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def is_video_url(url: str) -> bool:
    """Check if URL is a YouTube video URL."""
    return extract_video_id(url) is not None


router = APIRouter()


@router.get("", response_model=ChannelListResponse)
async def list_channels(db: DB):
    """List all channels."""
    result = await db.execute(select(Channel).order_by(Channel.created_at.desc()))
    channels = result.scalars().all()

    return ChannelListResponse(
        channels=[ChannelResponse.model_validate(c) for c in channels],
        total=len(channels),
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: UUID, db: DB):
    """Get channel by ID."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    return ChannelResponse.model_validate(channel)


@router.get("/slug/{slug}", response_model=ChannelResponse)
async def get_channel_by_slug(slug: str, db: DB):
    """Get channel by slug."""
    result = await db.execute(select(Channel).where(Channel.slug == slug))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    return ChannelResponse.model_validate(channel)


@router.post("/fetch-video")
async def fetch_video(
    request: ChannelFetchRequest,
    db: DB,
    _: AdminAuth,
):
    """
    Fetch a single video info from YouTube.
    Returns video info along with its channel info.
    """
    video_id = extract_video_id(request.youtube_url)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube video URL.",
        )

    youtube = YouTubeService()

    try:
        # Get video info
        video_info = await youtube.get_video_info(video_id)

        if not video_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found.",
            )

        # Check if video already exists
        existing_episode = await db.execute(
            select(Episode).where(Episode.youtube_id == video_id)
        )
        existing_ep = existing_episode.scalar_one_or_none()

        # Check if channel exists
        existing_channel = None
        if video_info.channel_id:
            channel_result = await db.execute(
                select(Channel).where(
                    Channel.youtube_channel_id == video_info.channel_id
                )
            )
            existing_channel = channel_result.scalar_one_or_none()

        return {
            "video": {
                "youtube_id": video_id,
                "title": video_info.title,
                "description": video_info.description,
                "duration_seconds": video_info.duration_seconds,
                "published_at": (
                    video_info.published_at.isoformat()
                    if video_info.published_at
                    else None
                ),
                "thumbnail_url": video_info.thumbnail_url,
                "already_exists": existing_ep is not None,
                "existing_episode_id": str(existing_ep.id) if existing_ep else None,
            },
            "channel": {
                "name": video_info.channel_name or "Unknown Channel",
                "youtube_channel_id": video_info.channel_id,
                "thumbnail_url": None,  # Not available from video info
                "already_exists": existing_channel is not None,
                "existing_channel_id": (
                    str(existing_channel.id) if existing_channel else None
                ),
                "existing_channel_slug": (
                    existing_channel.slug if existing_channel else None
                ),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch video: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch video. Please check the URL and try again.",
        )


@router.post("/fetch", response_model=ChannelFetchResponse)
async def fetch_channel(
    request: ChannelFetchRequest,
    db: DB,
    _: AdminAuth,
):
    """
    Fetch channel info and episodes from YouTube.
    Does not create the channel yet - just returns preview data.
    """
    # Validate YouTube URL format
    if not validate_youtube_url(request.youtube_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube channel URL. Must be a valid YouTube channel, user, or handle URL.",
        )

    youtube = YouTubeService()

    try:
        # Get channel info
        channel_info = await youtube.get_channel_info(request.youtube_url)

        # Check if channel already exists
        existing = await db.execute(
            select(Channel).where(Channel.youtube_channel_id == channel_info.channel_id)
        )
        existing_channel = existing.scalar_one_or_none()

        # Fetch episodes
        episodes = await youtube.fetch_channel_episodes(
            channel_url=request.youtube_url,
            skip_shorts=True,
        )

        # If channel exists, mark episodes that are already in DB
        existing_episode_ids = set()
        if existing_channel:
            ep_result = await db.execute(
                select(Episode.youtube_id).where(
                    Episode.channel_id == existing_channel.id
                )
            )
            existing_episode_ids = set(ep_result.scalars().all())

        episode_previews = []
        for ep in episodes:
            episode_previews.append(
                EpisodePreview(
                    id=(
                        UUID(int=0)
                        if ep.youtube_id not in existing_episode_ids
                        else UUID(int=1)
                    ),
                    youtube_id=ep.youtube_id,
                    title=ep.title,
                    duration_seconds=ep.duration_seconds,
                    published_at=ep.published_at,
                    thumbnail_url=ep.thumbnail_url,
                    selected=ep.youtube_id not in existing_episode_ids,
                )
            )

        return ChannelFetchResponse(
            channel_id=existing_channel.id if existing_channel else None,
            name=channel_info.name,
            youtube_channel_id=channel_info.channel_id,
            thumbnail_url=channel_info.thumbnail_url,
            description=channel_info.description,
            episodes=episode_previews,
            total_episodes=len(episode_previews),
            is_new=existing_channel is None,
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log full error details but don't expose to client
        logger.error(f"Failed to fetch channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch channel. Please check the URL and try again.",
        )


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    channel: ChannelCreate,
    db: DB,
    _: AdminAuth,
):
    """Create a new channel."""
    # Generate slug
    base_slug = slugify(channel.name)
    slug = base_slug

    # Ensure unique slug
    counter = 1
    while True:
        existing = await db.execute(select(Channel).where(Channel.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    db_channel = Channel(
        slug=slug,
        name=channel.name,
        description=channel.description,
        youtube_channel_id=channel.youtube_channel_id,
        youtube_url=channel.youtube_url,
        thumbnail_url=channel.thumbnail_url,
        speakers=channel.speakers,
        default_unknown_speaker_label=channel.default_unknown_speaker_label,
    )

    db.add(db_channel)
    await db.commit()
    await db.refresh(db_channel)

    return ChannelResponse.model_validate(db_channel)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    update: ChannelUpdate,
    db: DB,
    _: AdminAuth,
):
    """Update channel settings."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)

    return ChannelResponse.model_validate(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Delete channel and all associated data."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Delete from vector store
    from app.services.vector_store import VectorStoreService

    vector_store = VectorStoreService()
    await vector_store.delete_by_channel(str(channel_id))

    # Delete channel (cascades to episodes, utterances, etc.)
    await db.delete(channel)
    await db.commit()
