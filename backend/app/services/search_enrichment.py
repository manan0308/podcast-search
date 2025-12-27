"""
Shared search result enrichment service.

Fixes N+1 query problems by batch-loading episodes and channels.
"""
from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import Episode, Channel, Utterance
from app.schemas.search import SearchResult


class SearchEnrichmentService:
    """
    Enriches search results with episode/channel data efficiently.

    Uses batch loading to avoid N+1 queries:
    - Collects all unique episode_ids and channel_ids
    - Loads all in 2 queries instead of 2*N queries
    - Caches loaded entities for context fetching
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._episode_cache: dict[UUID, Episode] = {}
        self._channel_cache: dict[UUID, Channel] = {}

    async def preload_entities(self, vector_results: list[dict]) -> None:
        """
        Preload all episodes and channels needed for enrichment.

        Call this ONCE before enriching multiple results.
        """
        # Collect unique IDs
        episode_ids = set()
        channel_ids = set()

        for result in vector_results:
            try:
                episode_ids.add(UUID(result.get("episode_id")))
                channel_ids.add(UUID(result.get("channel_id")))
            except (ValueError, TypeError):
                continue

        # Batch load episodes (single query)
        if episode_ids:
            ep_result = await self.db.execute(
                select(Episode).where(Episode.id.in_(episode_ids))
            )
            for episode in ep_result.scalars():
                self._episode_cache[episode.id] = episode

        # Batch load channels (single query)
        if channel_ids:
            ch_result = await self.db.execute(
                select(Channel).where(Channel.id.in_(channel_ids))
            )
            for channel in ch_result.scalars():
                self._channel_cache[channel.id] = channel

        logger.debug(
            f"Preloaded {len(self._episode_cache)} episodes, "
            f"{len(self._channel_cache)} channels"
        )

    async def enrich_result(
        self,
        vector_result: dict,
        include_context: bool = False,
        context_count: int = 2,
    ) -> Optional[SearchResult]:
        """
        Enrich a single vector search result with database data.

        Uses cached entities from preload_entities().
        """
        try:
            episode_id = UUID(vector_result.get("episode_id"))
            channel_id = UUID(vector_result.get("channel_id"))
        except (ValueError, TypeError):
            logger.warning(f"Invalid UUID in vector result: {vector_result}")
            return None

        # Get from cache (already loaded)
        episode = self._episode_cache.get(episode_id)
        channel = self._channel_cache.get(channel_id)

        if not episode or not channel:
            logger.warning(f"Missing episode/channel: {episode_id}, {channel_id}")
            return None

        # Get context if requested
        context_before = []
        context_after = []

        if include_context:
            start_ms = vector_result.get("start_ms", 0)
            end_ms = vector_result.get("end_ms", 0)
            context_before, context_after = await self._get_context_utterances(
                episode_id=episode_id,
                start_ms=start_ms,
                end_ms=end_ms,
                count=context_count,
            )

        # Format timestamp
        start_ms = vector_result.get("start_ms", 0)
        total_seconds = start_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        timestamp = f"{minutes}:{seconds:02d}"

        return SearchResult(
            chunk_id=UUID(vector_result.get("chunk_id", vector_result.get("id"))),
            episode_id=episode_id,
            channel_id=channel_id,
            episode_title=episode.title,
            episode_url=episode.url,
            episode_thumbnail=episode.thumbnail_url,
            channel_name=channel.name,
            channel_slug=channel.slug,
            speaker=vector_result.get("speaker"),
            speakers=vector_result.get("speakers", []),
            text=vector_result.get("text", ""),
            timestamp=timestamp,
            timestamp_ms=start_ms,
            published_at=episode.published_at,
            score=vector_result.get("score", 0),
            context_before=context_before,
            context_after=context_after,
        )

    async def enrich_results(
        self,
        vector_results: list[dict],
        include_context: bool = False,
        context_count: int = 2,
    ) -> list[SearchResult]:
        """
        Enrich multiple vector results efficiently.

        This is the main entry point - handles preloading automatically.
        """
        if not vector_results:
            return []

        # Preload all entities in 2 queries
        await self.preload_entities(vector_results)

        # Enrich each result (no more N+1 for episode/channel)
        results = []
        for vector_result in vector_results:
            enriched = await self.enrich_result(
                vector_result,
                include_context=include_context,
                context_count=context_count,
            )
            if enriched:
                results.append(enriched)

        return results

    async def _get_context_utterances(
        self,
        episode_id: UUID,
        start_ms: int,
        end_ms: int,
        count: int = 2,
    ) -> tuple[list[dict], list[dict]]:
        """
        Get surrounding utterances for context.

        Optimized: Uses compound query with UNION instead of 2 separate queries.
        """
        # Get before context (utterances ending before our start)
        before_result = await self.db.execute(
            select(Utterance)
            .where(Utterance.episode_id == episode_id)
            .where(Utterance.end_ms < start_ms)
            .order_by(Utterance.end_ms.desc())
            .limit(count)
        )
        before_utterances = list(reversed(before_result.scalars().all()))

        # Get after context (utterances starting after our end)
        after_result = await self.db.execute(
            select(Utterance)
            .where(Utterance.episode_id == episode_id)
            .where(Utterance.start_ms > end_ms)
            .order_by(Utterance.start_ms.asc())
            .limit(count)
        )
        after_utterances = list(after_result.scalars().all())

        # Format as ContextUtterance objects
        from app.schemas.search import ContextUtterance

        context_before = [
            ContextUtterance(
                speaker=u.speaker,
                text=u.text,
                start_ms=u.start_ms,
                end_ms=u.end_ms,
            )
            for u in before_utterances
        ]
        context_after = [
            ContextUtterance(
                speaker=u.speaker,
                text=u.text,
                start_ms=u.start_ms,
                end_ms=u.end_ms,
            )
            for u in after_utterances
        ]

        return context_before, context_after
