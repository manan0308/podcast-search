import asyncio
from datetime import datetime
from uuid import UUID
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.models import Batch, Job, Episode
from app.workers.pipeline import TranscriptionPipeline


# Create a separate engine for background tasks
ASYNC_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
)

background_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=5,
)

BackgroundSessionLocal = async_sessionmaker(
    bind=background_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def process_batch(batch_id: str):
    """
    Process all pending jobs in a batch.

    This runs as a background task and processes jobs with
    the configured concurrency limit.
    """
    logger.info(f"Starting batch processing: {batch_id}")

    async with BackgroundSessionLocal() as db:
        # Get batch
        result = await db.execute(
            select(Batch).where(Batch.id == UUID(batch_id))
        )
        batch = result.scalar_one_or_none()

        if not batch:
            logger.error(f"Batch not found: {batch_id}")
            return

        if batch.status != "running":
            logger.info(f"Batch {batch_id} is not running (status: {batch.status})")
            return

        # Get batch config
        provider = batch.provider
        concurrency = batch.concurrency
        speakers = batch.config.get("speakers", [])

        logger.info(f"Processing batch {batch_id} with {provider}, concurrency={concurrency}")

        # Get pending jobs
        jobs_result = await db.execute(
            select(Job)
            .where(Job.batch_id == batch.id)
            .where(Job.status == "pending")
            .order_by(Job.created_at)
        )
        pending_jobs = list(jobs_result.scalars().all())

        logger.info(f"Found {len(pending_jobs)} pending jobs")

        # Process jobs with concurrency control
        semaphore = asyncio.Semaphore(concurrency)

        async def process_job(job: Job):
            async with semaphore:
                # Check if batch is still running with row lock to prevent race condition
                async with BackgroundSessionLocal() as check_db:
                    from sqlalchemy import text
                    batch_check = await check_db.execute(
                        text("SELECT status FROM batches WHERE id = :batch_id FOR UPDATE SKIP LOCKED"),
                        {"batch_id": str(batch.id)}
                    )
                    row = batch_check.fetchone()
                    current_status = row[0] if row else None

                if current_status != "running":
                    logger.info(f"Batch {batch_id} is no longer running, skipping job")
                    return False

                # Create a new session for this job
                async with BackgroundSessionLocal() as job_db:
                    pipeline = TranscriptionPipeline(
                        db=job_db,
                        provider_name=provider,
                        speakers=speakers,
                    )

                    success = await pipeline.process_episode(
                        job_id=job.id,
                        episode_id=job.episode_id,
                    )

                    return success

        # Create tasks for all pending jobs
        tasks = [process_job(job) for job in pending_jobs]

        # Process with progress tracking
        completed = 0
        failed = 0

        for coro in asyncio.as_completed(tasks):
            try:
                success = await coro
                if success:
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Job failed with error: {e}")
                failed += 1

            # Update batch stats atomically using SQL UPDATE (prevents race conditions)
            async with BackgroundSessionLocal() as stats_db:
                from sqlalchemy import text
                if success:
                    await stats_db.execute(
                        text("""
                            UPDATE batches
                            SET completed_episodes = completed_episodes + 1
                            WHERE id = :batch_id
                        """),
                        {"batch_id": batch_id}
                    )
                else:
                    await stats_db.execute(
                        text("""
                            UPDATE batches
                            SET failed_episodes = failed_episodes + 1
                            WHERE id = :batch_id
                        """),
                        {"batch_id": batch_id}
                    )
                await stats_db.commit()

        # Final batch status update
        async with BackgroundSessionLocal() as final_db:
            batch_result = await final_db.execute(
                select(Batch).where(Batch.id == UUID(batch_id))
            )
            batch_final = batch_result.scalar_one_or_none()

            if batch_final and batch_final.status == "running":
                batch_final.status = "completed"
                batch_final.completed_at = datetime.utcnow()
                batch_final.completed_episodes = completed
                batch_final.failed_episodes = failed

                # Calculate actual cost
                jobs_result = await final_db.execute(
                    select(Job.cost_cents)
                    .where(Job.batch_id == batch_final.id)
                    .where(Job.cost_cents.isnot(None))
                )
                costs = [c for c in jobs_result.scalars() if c]
                batch_final.actual_cost_cents = sum(costs)

                await final_db.commit()

    logger.info(f"Batch {batch_id} completed: {completed} success, {failed} failed")


async def retry_failed_jobs(batch_id: str):
    """Retry all failed jobs in a batch."""
    async with BackgroundSessionLocal() as db:
        # Get failed jobs
        result = await db.execute(
            select(Job)
            .where(Job.batch_id == UUID(batch_id))
            .where(Job.status == "failed")
            .where(Job.retry_count < 3)
        )
        failed_jobs = result.scalars().all()

        logger.info(f"Retrying {len(failed_jobs)} failed jobs in batch {batch_id}")

        for job in failed_jobs:
            job.status = "pending"
            job.progress = 0
            job.current_step = None
            job.error_message = None
            job.error_code = None
            job.started_at = None
            job.completed_at = None
            job.retry_count += 1

            # Update episode status
            ep_result = await db.execute(
                select(Episode).where(Episode.id == job.episode_id)
            )
            episode = ep_result.scalar_one_or_none()
            if episode:
                episode.status = "queued"

        # Update batch status
        batch_result = await db.execute(
            select(Batch).where(Batch.id == UUID(batch_id))
        )
        batch = batch_result.scalar_one_or_none()
        if batch:
            batch.status = "running"
            batch.failed_episodes = 0

        await db.commit()

    # Start processing
    await process_batch(batch_id)
