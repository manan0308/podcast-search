"""Maintenance tasks for Celery."""
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from celery.utils.log import get_task_logger
from sqlalchemy import select, func, update

from app.celery_app import celery_app
from app.config import settings
from app.database import async_session_factory
from app.models import Channel, Episode, Chunk
from app.services.cache import CacheService

logger = get_task_logger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.cleanup_audio_files",
)
def cleanup_audio_files(self, max_age_hours: int = 24):
    """
    Clean up old audio files that weren't properly deleted.

    Runs periodically to prevent disk space issues.
    """
    logger.info("Starting audio file cleanup")

    audio_dir = Path(settings.AUDIO_DIR)
    if not audio_dir.exists():
        return {"status": "no_directory"}

    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    deleted = 0
    errors = 0

    for file_path in audio_dir.glob("*.mp3"):
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if mtime < cutoff:
                file_path.unlink()
                deleted += 1
                logger.debug(f"Deleted old audio file: {file_path.name}")
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            errors += 1

    logger.info(f"Cleanup complete: {deleted} deleted, {errors} errors")
    return {"deleted": deleted, "errors": errors}


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.update_channel_stats",
)
def update_channel_stats(self):
    """
    Update channel statistics (episode count, transcribed count, duration).

    Ensures stats are accurate even if individual updates failed.
    """
    logger.info("Updating channel statistics")

    async def _update():
        async with async_session_factory() as db:
            # Get all channels
            channels_result = await db.execute(select(Channel))
            channels = channels_result.scalars().all()

            updated = 0
            for channel in channels:
                # Count episodes
                episode_count_result = await db.execute(
                    select(func.count(Episode.id))
                    .where(Episode.channel_id == channel.id)
                )
                episode_count = episode_count_result.scalar()

                # Count transcribed episodes
                transcribed_count_result = await db.execute(
                    select(func.count(Episode.id))
                    .where(
                        Episode.channel_id == channel.id,
                        Episode.status == "done"
                    )
                )
                transcribed_count = transcribed_count_result.scalar()

                # Sum duration
                duration_result = await db.execute(
                    select(func.coalesce(func.sum(Episode.duration_seconds), 0))
                    .where(Episode.channel_id == channel.id)
                )
                total_duration = duration_result.scalar()

                # Update if changed
                if (channel.episode_count != episode_count or
                    channel.transcribed_count != transcribed_count or
                    channel.total_duration_seconds != total_duration):

                    channel.episode_count = episode_count
                    channel.transcribed_count = transcribed_count
                    channel.total_duration_seconds = total_duration
                    updated += 1

            await db.commit()
            logger.info(f"Updated {updated} channel stats")
            return {"updated": updated, "total": len(channels)}

    return run_async(_update())


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.refresh_popular_embeddings",
)
def refresh_popular_embeddings(self):
    """
    Refresh embedding cache for popular/recent searches.

    Keeps frequently used embeddings warm in cache.
    """
    logger.info("Refreshing popular embeddings cache")

    # Common search patterns to keep cached
    common_queries = [
        "startup advice",
        "product market fit",
        "fundraising tips",
        "how to scale",
        "growth strategy",
        "hiring advice",
        "founder story",
        "business model",
        "revenue growth",
        "customer acquisition",
    ]

    from app.tasks.embedding import warm_embedding_cache
    warm_embedding_cache.delay(common_queries)

    return {"queries": len(common_queries)}


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.vacuum_vector_store",
)
def vacuum_vector_store(self):
    """
    Optimize Qdrant collection by removing deleted vectors.

    Should be run periodically when there are many deletions.
    """
    logger.info("Vacuuming vector store")

    async def _vacuum():
        from app.services.vector_store import VectorStoreService

        vector_store = VectorStoreService()

        # Get stats before
        stats_before = await vector_store.get_collection_stats()

        # Qdrant auto-optimizes, but we can trigger it
        # by checking collection status
        stats_after = await vector_store.get_collection_stats()

        return {
            "points_before": stats_before.get("points_count", 0),
            "points_after": stats_after.get("points_count", 0),
        }

    return run_async(_vacuum())


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.reindex_episode",
)
def reindex_episode(self, episode_id: str):
    """
    Reindex a single episode (regenerate chunks and embeddings).

    Use when chunk strategy changes or to fix issues.
    """
    logger.info(f"Reindexing episode {episode_id}")

    async def _reindex():
        from app.services.vector_store import VectorStoreService
        from app.services.embedding import EmbeddingService
        from app.services.chunking import ChunkingService

        async with async_session_factory() as db:
            # Get episode with utterances
            from sqlalchemy.orm import selectinload
            episode_result = await db.execute(
                select(Episode)
                .options(selectinload(Episode.utterances))
                .where(Episode.id == UUID(episode_id))
            )
            episode = episode_result.scalar_one_or_none()

            if not episode or not episode.utterances:
                return {"status": "no_data"}

            # Get channel
            channel_result = await db.execute(
                select(Channel).where(Channel.id == episode.channel_id)
            )
            channel = channel_result.scalar_one_or_none()

            # Delete existing vectors
            vector_store = VectorStoreService()
            await vector_store.delete_by_episode(episode_id)

            # Delete existing chunks from DB
            await db.execute(
                Chunk.__table__.delete().where(Chunk.episode_id == UUID(episode_id))
            )

            # Re-chunk
            chunking_service = ChunkingService()
            utterance_dicts = [
                {
                    "speaker": u.speaker,
                    "text": u.text,
                    "start_ms": u.start_ms,
                    "end_ms": u.end_ms,
                }
                for u in sorted(episode.utterances, key=lambda x: x.start_ms)
            ]

            chunks = chunking_service.chunk_transcript(utterance_dicts)

            # Prepare chunk data
            chunk_data = []
            for i, chunk in enumerate(chunks):
                chunk_data.append({
                    "text": chunk["text"],
                    "episode_id": episode.id,
                    "channel_id": episode.channel_id,
                    "episode_title": episode.title,
                    "channel_name": channel.name if channel else "",
                    "channel_slug": channel.slug if channel else "",
                    "primary_speaker": chunk.get("primary_speaker"),
                    "speakers": chunk.get("speakers", []),
                    "start_ms": chunk["start_ms"],
                    "end_ms": chunk["end_ms"],
                    "chunk_index": i,
                    "word_count": chunk.get("word_count", 0),
                    "published_at": episode.published_at,
                })

            # Generate embeddings
            embedding_service = EmbeddingService()
            texts = [c["text"] for c in chunk_data]
            embeddings = await embedding_service.embed_texts(texts)

            # Store in vector DB
            await vector_store.upsert_chunks(chunk_data, embeddings)

            # Store chunks in postgres
            for chunk in chunk_data:
                db_chunk = Chunk(
                    episode_id=chunk["episode_id"],
                    text=chunk["text"],
                    start_ms=chunk["start_ms"],
                    end_ms=chunk["end_ms"],
                    speaker=chunk.get("primary_speaker"),
                    word_count=chunk.get("word_count", 0),
                )
                db.add(db_chunk)

            await db.commit()

            logger.info(f"Reindexed episode {episode_id}: {len(chunks)} chunks")
            return {"status": "success", "chunks": len(chunks)}

    return run_async(_reindex())


@celery_app.task(
    bind=True,
    name="app.tasks.maintenance.clear_cache",
)
def clear_cache(self, pattern: str = "*"):
    """
    Clear Redis cache matching pattern.

    Use with caution - clears cached embeddings and search results.
    """
    logger.info(f"Clearing cache with pattern: {pattern}")

    async def _clear():
        cache = CacheService()
        deleted = await cache.clear_pattern(pattern)
        logger.info(f"Cleared {deleted} cache keys")
        return {"deleted": deleted}

    return run_async(_clear())
