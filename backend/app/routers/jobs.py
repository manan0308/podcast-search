from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func

from app.dependencies import DB, AdminAuth
from app.models import Job, Episode, Batch, ActivityLog
from app.schemas.job import (
    JobResponse,
    JobListResponse,
    JobDetailResponse,
    ActivityLogResponse,
    ActivityLogListResponse,
)

router = APIRouter()


@router.get("", response_model=JobListResponse)
async def list_jobs(
    db: DB,
    batch_id: UUID | None = None,
    episode_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List jobs with filtering."""
    query = select(Job)

    if batch_id:
        query = query.where(Job.batch_id == batch_id)

    if episode_id:
        query = query.where(Job.episode_id == episode_id)

    if status_filter:
        query = query.where(Job.status == status_filter)

    # Get total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Job.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: UUID, db: DB):
    """Get job details."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    # Get episode info
    ep_result = await db.execute(select(Episode).where(Episode.id == job.episode_id))
    episode = ep_result.scalar_one_or_none()

    # Get batch info
    batch_name = None
    if job.batch_id:
        batch_result = await db.execute(
            select(Batch.name).where(Batch.id == job.batch_id)
        )
        batch_name = batch_result.scalar_one_or_none()

    return JobDetailResponse(
        id=job.id,
        batch_id=job.batch_id,
        episode_id=job.episode_id,
        provider=job.provider,
        provider_job_id=job.provider_job_id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        error_code=job.error_code,
        retry_count=job.retry_count,
        cost_cents=job.cost_cents,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        duration_seconds=job.duration_seconds,
        episode_title=episode.title if episode else "Unknown",
        episode_youtube_id=episode.youtube_id if episode else "Unknown",
        batch_name=batch_name,
    )


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Retry a failed job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Can only retry failed jobs"
        )

    # Reset job
    job.status = "pending"
    job.progress = 0
    job.current_step = None
    job.error_message = None
    job.error_code = None
    job.started_at = None
    job.completed_at = None
    job.retry_count += 1

    # Update episode status
    ep_result = await db.execute(select(Episode).where(Episode.id == job.episode_id))
    episode = ep_result.scalar_one_or_none()
    if episode:
        episode.status = "queued"

    await db.commit()

    return {"status": "queued", "job_id": str(job_id)}


@router.get("/{job_id}/logs", response_model=ActivityLogListResponse)
async def get_job_logs(
    job_id: UUID,
    db: DB,
    limit: int = Query(100, ge=1, le=500),
):
    """Get activity logs for a job."""
    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.job_id == job_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return ActivityLogListResponse(
        logs=[ActivityLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Pause a running job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status not in (
        "processing",
        "transcribing",
        "downloading",
        "embedding",
        "chunking",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause job with status: {job.status}",
        )

    job.status = "paused"

    await db.commit()

    return {"status": "paused", "job_id": str(job_id)}


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Resume a paused job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume job with status: {job.status}",
        )

    job.status = "pending"

    # Update episode status
    ep_result = await db.execute(select(Episode).where(Episode.id == job.episode_id))
    episode = ep_result.scalar_one_or_none()
    if episode:
        episode.status = "queued"

    await db.commit()

    return {"status": "pending", "job_id": str(job_id)}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    db: DB,
    _: AdminAuth,
):
    """Cancel a pending or running job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status in ("done", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}",
        )

    job.status = "cancelled"

    # Update episode status
    ep_result = await db.execute(select(Episode).where(Episode.id == job.episode_id))
    episode = ep_result.scalar_one_or_none()
    if episode:
        episode.status = "skipped"

    await db.commit()

    return {"status": "cancelled", "job_id": str(job_id)}
