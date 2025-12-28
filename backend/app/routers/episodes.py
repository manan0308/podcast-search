from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DB, AdminAuth
from app.models import Episode, Channel
from app.schemas.episode import (
    EpisodeResponse,
    EpisodeListResponse,
    EpisodeDetailResponse,
    UtteranceResponse,
    EpisodeCreate,
    EpisodeBulkCreate,
)

router = APIRouter()


@router.post("", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    episode: EpisodeCreate,
    db: DB,
    _: AdminAuth,
):
    """Create a new episode."""
    # Verify channel exists
    channel_result = await db.execute(
        select(Channel).where(Channel.id == episode.channel_id)
    )
    channel = channel_result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Check if episode already exists
    existing = await db.execute(
        select(Episode).where(
            Episode.channel_id == episode.channel_id,
            Episode.youtube_id == episode.youtube_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Episode already exists"
        )

    db_episode = Episode(
        channel_id=episode.channel_id,
        youtube_id=episode.youtube_id,
        title=episode.title,
        description=episode.description,
        url=episode.url or f"https://www.youtube.com/watch?v={episode.youtube_id}",
        thumbnail_url=episode.thumbnail_url,
        published_at=episode.published_at,
        duration_seconds=episode.duration_seconds,
        status="pending",
    )

    db.add(db_episode)

    # Update channel stats
    channel.episode_count += 1
    if episode.duration_seconds:
        channel.total_duration_seconds += episode.duration_seconds

    await db.commit()
    await db.refresh(db_episode)

    return EpisodeResponse.model_validate(db_episode)


@router.post(
    "/bulk", response_model=list[EpisodeResponse], status_code=status.HTTP_201_CREATED
)
async def create_episodes_bulk(
    bulk: EpisodeBulkCreate,
    db: DB,
    _: AdminAuth,
):
    """Create multiple episodes at once."""
    # Verify channel exists
    channel_result = await db.execute(
        select(Channel).where(Channel.id == bulk.channel_id)
    )
    channel = channel_result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Get existing youtube IDs for this channel
    existing_result = await db.execute(
        select(Episode.youtube_id).where(Episode.channel_id == bulk.channel_id)
    )
    existing_ids = set(existing_result.scalars().all())

    created = []
    total_duration = 0

    for ep in bulk.episodes:
        if ep.youtube_id in existing_ids:
            continue

        db_episode = Episode(
            channel_id=bulk.channel_id,
            youtube_id=ep.youtube_id,
            title=ep.title,
            description=ep.description,
            url=ep.url or f"https://www.youtube.com/watch?v={ep.youtube_id}",
            thumbnail_url=ep.thumbnail_url,
            published_at=ep.published_at,
            duration_seconds=ep.duration_seconds,
            status="pending",
        )
        db.add(db_episode)
        created.append(db_episode)

        if ep.duration_seconds:
            total_duration += ep.duration_seconds

    # Update channel stats
    channel.episode_count += len(created)
    channel.total_duration_seconds += total_duration

    await db.commit()

    # Refresh created episodes
    for ep in created:
        await db.refresh(ep)

    return [EpisodeResponse.model_validate(ep) for ep in created]


@router.get("", response_model=EpisodeListResponse)
async def list_episodes(
    db: DB,
    channel_id: UUID | None = None,
    channel_slug: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List episodes with filtering and pagination.

    Filter by:
    - channel_id or channel_slug
    - status (pending, queued, processing, done, failed, skipped)
    - search (title search)
    """
    query = select(Episode)

    # Filter by channel
    if channel_id:
        query = query.where(Episode.channel_id == channel_id)
    elif channel_slug:
        channel_result = await db.execute(
            select(Channel).where(Channel.slug == channel_slug)
        )
        channel = channel_result.scalar_one_or_none()
        if channel:
            query = query.where(Episode.channel_id == channel.id)

    # Filter by status
    if status_filter:
        query = query.where(Episode.status == status_filter)

    # Search in title (escape LIKE special characters to prevent pattern injection)
    if search:
        # Escape special LIKE characters: % _ \
        escaped_search = (
            search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        query = query.where(Episode.title.ilike(f"%{escaped_search}%", escape="\\"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Episode.published_at.desc().nullslast())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    episodes = result.scalars().all()

    return EpisodeListResponse(
        episodes=[EpisodeResponse.model_validate(ep) for ep in episodes],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{episode_id}", response_model=EpisodeDetailResponse)
async def get_episode(episode_id: UUID, db: DB):
    """Get episode details with full transcript."""
    result = await db.execute(
        select(Episode)
        .options(selectinload(Episode.utterances))
        .where(Episode.id == episode_id)
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found"
        )

    # Get channel info
    channel_result = await db.execute(
        select(Channel).where(Channel.id == episode.channel_id)
    )
    channel = channel_result.scalar_one_or_none()

    # Sort utterances by start time
    sorted_utterances = sorted(episode.utterances, key=lambda u: u.start_ms)

    # Build response
    utterance_responses = []
    for u in sorted_utterances:
        # Calculate timestamp
        total_seconds = u.start_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        timestamp = f"{minutes}:{seconds:02d}"

        utterance_responses.append(
            UtteranceResponse(
                id=u.id,
                speaker=u.speaker,
                speaker_raw=u.speaker_raw,
                text=u.text,
                start_ms=u.start_ms,
                end_ms=u.end_ms,
                confidence=u.confidence,
                timestamp=timestamp,
            )
        )

    return EpisodeDetailResponse(
        id=episode.id,
        channel_id=episode.channel_id,
        youtube_id=episode.youtube_id,
        title=episode.title,
        description=episode.description,
        url=episode.url,
        thumbnail_url=episode.thumbnail_url,
        published_at=episode.published_at,
        duration_seconds=episode.duration_seconds,
        status=episode.status,
        word_count=episode.word_count,
        created_at=episode.created_at,
        updated_at=episode.updated_at,
        processed_at=episode.processed_at,
        utterances=utterance_responses,
        channel_name=channel.name if channel else None,
        channel_slug=channel.slug if channel else None,
    )


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    episode_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Delete episode and all associated data."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found"
        )

    # Delete from vector store
    from app.services.vector_store import VectorStoreService

    vector_store = VectorStoreService()
    await vector_store.delete_by_episode(str(episode_id))

    # Update channel stats
    channel_result = await db.execute(
        select(Channel).where(Channel.id == episode.channel_id)
    )
    channel = channel_result.scalar_one_or_none()

    if channel:
        channel.episode_count = max(0, channel.episode_count - 1)
        if episode.status == "done":
            channel.transcribed_count = max(0, channel.transcribed_count - 1)
        if episode.duration_seconds:
            channel.total_duration_seconds = max(
                0, channel.total_duration_seconds - episode.duration_seconds
            )

    # Delete episode (cascades to utterances, chunks, jobs)
    await db.delete(episode)
    await db.commit()


@router.post("/{episode_id}/retry", response_model=EpisodeResponse)
async def retry_episode(
    episode_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Retry a failed episode."""
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found"
        )

    if episode.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry failed episodes",
        )

    # Reset status to pending
    episode.status = "pending"
    await db.commit()
    await db.refresh(episode)

    return EpisodeResponse.model_validate(episode)
