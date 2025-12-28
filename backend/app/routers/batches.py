from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, status, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from slugify import slugify
from loguru import logger

from app.dependencies import DB, AdminAuth
from app.models import Batch, Job, Episode, Channel
from app.schemas.batch import (
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchListResponse,
    JobSummary,
)
from app.services.transcription import get_provider

router = APIRouter()


@router.get("", response_model=BatchListResponse)
async def list_batches(
    db: DB,
    channel_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List batches with filtering."""
    query = select(Batch)

    if channel_id:
        query = query.where(Batch.channel_id == channel_id)

    if status_filter:
        query = query.where(Batch.status == status_filter)

    # Get total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Batch.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    batches = result.scalars().all()

    return BatchListResponse(
        batches=[BatchResponse.model_validate(b) for b in batches],
        total=total,
    )


@router.get("/{batch_id}", response_model=BatchDetailResponse)
async def get_batch(batch_id: UUID, db: DB):
    """Get batch details with jobs."""
    result = await db.execute(
        select(Batch).options(selectinload(Batch.jobs)).where(Batch.id == batch_id)
    )
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    # Get channel info
    channel_name = None
    if batch.channel_id:
        channel_result = await db.execute(
            select(Channel).where(Channel.id == batch.channel_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel:
            channel_name = channel.name

    # Batch load episode titles to fix N+1 query
    episode_ids = [job.episode_id for job in batch.jobs]
    if episode_ids:
        episodes_result = await db.execute(
            select(Episode.id, Episode.title).where(Episode.id.in_(episode_ids))
        )
        episode_titles = {row.id: row.title for row in episodes_result}
    else:
        episode_titles = {}

    # Get job details with pre-loaded episode titles
    jobs = []
    for job in sorted(batch.jobs, key=lambda j: j.created_at):
        episode_title = episode_titles.get(job.episode_id, "Unknown")

        jobs.append(
            JobSummary(
                id=job.id,
                episode_id=job.episode_id,
                episode_title=episode_title,
                status=job.status,
                progress=job.progress,
                current_step=job.current_step,
                error_message=job.error_message,
                cost_cents=job.cost_cents,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )
        )

    return BatchDetailResponse(
        id=batch.id,
        channel_id=batch.channel_id,
        name=batch.name,
        provider=batch.provider,
        concurrency=batch.concurrency,
        config=batch.config,
        total_episodes=batch.total_episodes,
        completed_episodes=batch.completed_episodes,
        failed_episodes=batch.failed_episodes,
        estimated_cost_cents=batch.estimated_cost_cents,
        actual_cost_cents=batch.actual_cost_cents,
        status=batch.status,
        progress_percent=batch.progress_percent,
        started_at=batch.started_at,
        paused_at=batch.paused_at,
        completed_at=batch.completed_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        jobs=jobs,
        channel_name=channel_name,
    )


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    batch_create: BatchCreate,
    db: DB,
    _: AdminAuth,
):
    """
    Create a new processing batch.

    Supports two modes:
    1. Existing channel/episodes: Provide channel_id and episode_ids
    2. New from YouTube: Provide channel_data and episodes_data (will auto-create)
    """
    # Verify provider is available
    try:
        provider = get_provider(batch_create.provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    channel = None
    episode_ids = []
    total_duration = 0

    # Mode 1: Existing channel and episodes
    if batch_create.channel_id and batch_create.episode_ids:
        channel_result = await db.execute(
            select(Channel).where(Channel.id == batch_create.channel_id)
        )
        channel = channel_result.scalar_one_or_none()

        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
            )

        episode_ids = batch_create.episode_ids

        for episode_id in episode_ids:
            ep_result = await db.execute(
                select(Episode).where(Episode.id == episode_id)
            )
            episode = ep_result.scalar_one_or_none()
            if episode and episode.duration_seconds:
                total_duration += episode.duration_seconds

    # Mode 2: Create channel and episodes from YouTube data
    elif batch_create.channel_data and batch_create.episodes_data:
        channel_data = batch_create.channel_data

        # Check if channel already exists
        existing_result = await db.execute(
            select(Channel).where(
                Channel.youtube_channel_id == channel_data.youtube_channel_id
            )
        )
        channel = existing_result.scalar_one_or_none()

        if not channel:
            # Create channel
            base_slug = slugify(channel_data.name)
            slug = base_slug
            counter = 1
            while True:
                existing = await db.execute(select(Channel).where(Channel.slug == slug))
                if not existing.scalar_one_or_none():
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1

            channel = Channel(
                slug=slug,
                name=channel_data.name,
                description=channel_data.description,
                youtube_channel_id=channel_data.youtube_channel_id,
                youtube_url=channel_data.youtube_url,
                thumbnail_url=channel_data.thumbnail_url,
                speakers=batch_create.speakers,
            )
            db.add(channel)
            await db.flush()
            logger.info(f"Created channel: {channel.name} (ID: {channel.id})")

        # Get existing episode youtube IDs for this channel
        existing_ep_result = await db.execute(
            select(Episode.youtube_id).where(Episode.channel_id == channel.id)
        )
        existing_youtube_ids = set(existing_ep_result.scalars().all())

        # Create episodes that don't exist
        created_episodes = []
        for ep_data in batch_create.episodes_data:
            if ep_data.youtube_id in existing_youtube_ids:
                # Get existing episode ID
                ep_result = await db.execute(
                    select(Episode).where(
                        Episode.channel_id == channel.id,
                        Episode.youtube_id == ep_data.youtube_id,
                    )
                )
                episode = ep_result.scalar_one()
                episode_ids.append(episode.id)
                if episode.duration_seconds:
                    total_duration += episode.duration_seconds
            else:
                # Create new episode
                episode = Episode(
                    channel_id=channel.id,
                    youtube_id=ep_data.youtube_id,
                    title=ep_data.title,
                    description=ep_data.description,
                    url=f"https://www.youtube.com/watch?v={ep_data.youtube_id}",
                    thumbnail_url=ep_data.thumbnail_url,
                    published_at=ep_data.published_at,
                    duration_seconds=ep_data.duration_seconds,
                    status="pending",
                )
                db.add(episode)
                created_episodes.append(episode)

                if ep_data.duration_seconds:
                    total_duration += ep_data.duration_seconds

        # Flush to get IDs
        await db.flush()

        # Add created episode IDs
        for ep in created_episodes:
            episode_ids.append(ep.id)

        # Update channel stats
        channel.episode_count += len(created_episodes)
        channel.total_duration_seconds += sum(
            ep.duration_seconds or 0 for ep in created_episodes
        )

        logger.info(
            f"Created {len(created_episodes)} episodes for channel {channel.name}"
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either (channel_id + episode_ids) or (channel_data + episodes_data)",
        )

    if not episode_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No episodes to process"
        )

    estimated_cost = provider.estimate_cost(total_duration)

    # Create batch
    batch = Batch(
        channel_id=channel.id,
        name=f"Batch - {channel.name} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        provider=batch_create.provider,
        concurrency=batch_create.concurrency,
        config={
            "speakers": batch_create.speakers,
            **batch_create.config,
        },
        total_episodes=len(episode_ids),
        estimated_cost_cents=estimated_cost,
        status="pending",
    )

    db.add(batch)
    await db.flush()

    # Create jobs for each episode
    for episode_id in episode_ids:
        job = Job(
            batch_id=batch.id,
            episode_id=episode_id,
            provider=batch_create.provider,
            status="pending",
        )
        db.add(job)

        # Update episode status
        ep_result = await db.execute(select(Episode).where(Episode.id == episode_id))
        episode = ep_result.scalar_one_or_none()
        if episode:
            episode.status = "queued"

    await db.commit()
    await db.refresh(batch)

    return BatchResponse.model_validate(batch)


@router.post("/{batch_id}/start")
async def start_batch(
    batch_id: UUID,
    db: DB,
    background_tasks: BackgroundTasks,
    _: AdminAuth,
):
    """Start processing a pending batch."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    if batch.status not in ("pending", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start batch with status: {batch.status}",
        )

    # Update batch status
    batch.status = "running"
    batch.started_at = datetime.utcnow()
    batch.paused_at = None
    await db.commit()

    # Start background processing
    from app.workers.batch_processor import process_batch

    background_tasks.add_task(process_batch, str(batch_id))

    return {"status": "started", "batch_id": str(batch_id)}


@router.post("/{batch_id}/pause")
async def pause_batch(
    batch_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Pause a running batch."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    if batch.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause running batches",
        )

    batch.status = "paused"
    batch.paused_at = datetime.utcnow()
    await db.commit()

    return {"status": "paused", "batch_id": str(batch_id)}


@router.post("/{batch_id}/resume")
async def resume_batch(
    batch_id: UUID,
    db: DB,
    background_tasks: BackgroundTasks,
    _: AdminAuth,
):
    """Resume a paused batch."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    if batch.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused batches",
        )

    batch.status = "running"
    batch.paused_at = None
    await db.commit()

    # Resume background processing
    from app.workers.batch_processor import process_batch

    background_tasks.add_task(process_batch, str(batch_id))

    return {"status": "resumed", "batch_id": str(batch_id)}


@router.post("/{batch_id}/cancel")
async def cancel_batch(
    batch_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Cancel a batch."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    if batch.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel batch with status: {batch.status}",
        )

    batch.status = "cancelled"
    batch.completed_at = datetime.utcnow()

    # Cancel pending jobs
    jobs_result = await db.execute(
        select(Job).where(
            Job.batch_id == batch_id,
            Job.status.in_(["pending", "downloading", "uploading"]),
        )
    )
    for job in jobs_result.scalars():
        job.status = "cancelled"

    await db.commit()

    return {"status": "cancelled", "batch_id": str(batch_id)}


@router.post("/{batch_id}/retry")
async def retry_batch(
    batch_id: UUID,
    db: DB,
    background_tasks: BackgroundTasks,
    _: AdminAuth,
):
    """Retry all failed/cancelled jobs in a batch."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    # Get failed/cancelled jobs
    jobs_result = await db.execute(
        select(Job).where(
            Job.batch_id == batch_id, Job.status.in_(["failed", "cancelled"])
        )
    )
    jobs = jobs_result.scalars().all()

    if not jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No failed or cancelled jobs to retry",
        )

    # Reset jobs to pending
    retry_count = 0
    for job in jobs:
        job.status = "pending"
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.progress = 0
        job.current_step = None
        retry_count += 1

    # Reset batch status if it was failed/cancelled
    if batch.status in ("failed", "cancelled", "completed"):
        batch.status = "running"
        batch.completed_at = None
        batch.failed_episodes = max(0, batch.failed_episodes - retry_count)

    await db.commit()

    # Start batch processing
    from app.workers.batch_processor import process_batch

    background_tasks.add_task(process_batch, str(batch_id))

    return {
        "status": "retrying",
        "batch_id": str(batch_id),
        "jobs_retried": retry_count,
    }


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Delete a batch (must be completed or cancelled)."""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )

    if batch.status in ("running", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete active batch. Cancel it first.",
        )

    await db.delete(batch)
    await db.commit()
