"""Transcription tasks for Celery."""

from uuid import UUID
from celery import group
from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import async_session_factory
from app.models import Batch, Job, Episode, Channel
from app.workers.pipeline import TranscriptionPipeline
from app.tasks.async_helpers import run_async  # Efficient async runner

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.transcription.process_episode",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def process_episode_task(
    self, episode_id: str, job_id: str, provider: str, config: dict
):
    """
    Process a single episode through the transcription pipeline.

    This task:
    1. Downloads audio from YouTube
    2. Transcribes with the specified provider
    3. Identifies speakers with Claude
    4. Chunks and embeds the transcript
    5. Stores in vector database
    """
    logger.info(f"Processing episode {episode_id} with job {job_id}")

    async def _process():
        async with async_session_factory() as db:
            try:
                # Get job and episode
                job_result = await db.execute(select(Job).where(Job.id == UUID(job_id)))
                job = job_result.scalar_one_or_none()

                if not job:
                    raise ValueError(f"Job {job_id} not found")

                episode_result = await db.execute(
                    select(Episode).where(Episode.id == UUID(episode_id))
                )
                episode = episode_result.scalar_one_or_none()

                if not episode:
                    raise ValueError(f"Episode {episode_id} not found")

                # Get channel for speaker config
                channel_result = await db.execute(
                    select(Channel).where(Channel.id == episode.channel_id)
                )
                channel = channel_result.scalar_one_or_none()

                # Update job status
                job.status = "processing"
                job.current_step = "downloading"
                await db.commit()

                # Create pipeline and process
                pipeline = TranscriptionPipeline(
                    db=db,
                    provider=provider,
                    speakers=config.get(
                        "speakers", channel.speakers if channel else []
                    ),
                    unknown_speaker_label=(
                        channel.default_unknown_speaker_label if channel else "Guest"
                    ),
                )

                # Process the episode
                await pipeline.process_episode(
                    episode=episode,
                    job=job,
                )

                logger.info(f"Successfully processed episode {episode_id}")
                return {"status": "success", "episode_id": episode_id}

            except Exception as e:
                logger.error(f"Failed to process episode {episode_id}: {e}")

                # Update job status
                if job:
                    job.status = "failed"
                    job.error_message = str(e)[:500]
                    await db.commit()

                raise

    return run_async(_process())


@celery_app.task(
    bind=True,
    name="app.tasks.transcription.process_batch",
    max_retries=1,
)
def process_batch_task(self, batch_id: str):
    """
    Process a batch by spawning tasks for each episode.

    This task:
    1. Gets all pending jobs for the batch
    2. Creates a Celery group to process them in parallel
    3. Monitors progress and updates batch status
    """
    logger.info(f"Starting batch processing: {batch_id}")

    async def _process():
        async with async_session_factory() as db:
            # Get batch
            batch_result = await db.execute(
                select(Batch).where(Batch.id == UUID(batch_id))
            )
            batch = batch_result.scalar_one_or_none()

            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            if batch.status not in ("pending", "running", "paused"):
                logger.info(f"Batch {batch_id} is {batch.status}, skipping")
                return {"status": "skipped", "reason": f"Batch is {batch.status}"}

            # Update batch status
            batch.status = "running"
            await db.commit()

            # Get pending jobs
            jobs_result = await db.execute(
                select(Job).where(
                    Job.batch_id == UUID(batch_id),
                    Job.status.in_(["pending", "failed"]),
                )
            )
            jobs = jobs_result.scalars().all()

            if not jobs:
                logger.info(f"No pending jobs for batch {batch_id}")
                batch.status = "completed"
                await db.commit()
                return {"status": "completed", "message": "No pending jobs"}

            logger.info(f"Found {len(jobs)} pending jobs for batch {batch_id}")

            # Build config
            config = batch.config or {}

            # Create task group
            job_tasks = []
            for job in jobs:
                task = process_episode_task.s(
                    episode_id=str(job.episode_id),
                    job_id=str(job.id),
                    provider=batch.provider,
                    config=config,
                )
                job_tasks.append(task)

            # Execute with concurrency limit
            _job_group = group(job_tasks)  # noqa: F841

            return {"status": "started", "job_count": len(jobs)}

    result = run_async(_process())

    # If we have jobs to process, execute them
    if result.get("status") == "started":
        # Get the group and apply it
        async def get_jobs():
            async with async_session_factory() as db:
                batch_result = await db.execute(
                    select(Batch).where(Batch.id == UUID(batch_id))
                )
                batch = batch_result.scalar_one_or_none()

                jobs_result = await db.execute(
                    select(Job).where(
                        Job.batch_id == UUID(batch_id),
                        Job.status.in_(["pending", "failed"]),
                    )
                )
                jobs = jobs_result.scalars().all()

                config = batch.config or {}

                return [
                    (str(j.episode_id), str(j.id), batch.provider, config) for j in jobs
                ]

        job_args = run_async(get_jobs())

        # Execute jobs in parallel (respecting concurrency via worker config)
        task_group = group(
            [
                process_episode_task.s(ep_id, job_id, provider, config)
                for ep_id, job_id, provider, config in job_args
            ]
        )

        # Apply the group and link to batch completion
        _group_result = task_group.apply_async()  # noqa: F841

        # Chain with batch completion check
        check_batch_completion.apply_async(
            args=[batch_id],
            countdown=10,  # Check after 10 seconds
        )

    return result


@celery_app.task(
    bind=True,
    name="app.tasks.transcription.check_batch_completion",
)
def check_batch_completion(self, batch_id: str):
    """Check if batch is complete and update status."""
    logger.info(f"Checking batch completion: {batch_id}")

    async def _check():
        async with async_session_factory() as db:
            batch_result = await db.execute(
                select(Batch).where(Batch.id == UUID(batch_id))
            )
            batch = batch_result.scalar_one_or_none()

            if not batch or batch.status not in ("running",):
                return {"status": "skipped"}

            # Count job statuses
            from sqlalchemy import func

            jobs_result = await db.execute(
                select(Job.status, func.count(Job.id))
                .where(Job.batch_id == UUID(batch_id))
                .group_by(Job.status)
            )
            status_counts = dict(jobs_result.all())

            total = sum(status_counts.values())
            completed = status_counts.get("completed", 0)
            failed = status_counts.get("failed", 0)
            pending = status_counts.get("pending", 0)
            processing = status_counts.get("processing", 0)

            # Update batch stats
            batch.completed_episodes = completed
            batch.failed_episodes = failed
            batch.progress_percent = (
                (completed + failed) / total * 100 if total > 0 else 0
            )

            # Check if all done
            if pending == 0 and processing == 0:
                batch.status = "completed"
                from datetime import datetime

                batch.completed_at = datetime.utcnow()
                logger.info(
                    f"Batch {batch_id} completed: {completed} success, {failed} failed"
                )
            else:
                # Re-check in 30 seconds
                check_batch_completion.apply_async(
                    args=[batch_id],
                    countdown=30,
                )

            await db.commit()

            return {
                "status": batch.status,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "processing": processing,
            }

    return run_async(_check())


@celery_app.task(
    bind=True,
    name="app.tasks.transcription.retry_failed_jobs",
)
def retry_failed_jobs(self, batch_id: str):
    """Retry all failed jobs in a batch."""
    logger.info(f"Retrying failed jobs for batch {batch_id}")

    async def _retry():
        async with async_session_factory() as db:
            # Get failed jobs
            jobs_result = await db.execute(
                select(Job).where(
                    Job.batch_id == UUID(batch_id), Job.status == "failed"
                )
            )
            jobs = jobs_result.scalars().all()

            if not jobs:
                return {"status": "no_failed_jobs"}

            # Reset job status
            for job in jobs:
                job.status = "pending"
                job.error_message = None
                job.retry_count += 1

            await db.commit()

            # Trigger batch processing
            process_batch_task.delay(batch_id)

            return {"status": "retrying", "job_count": len(jobs)}

    return run_async(_retry())
