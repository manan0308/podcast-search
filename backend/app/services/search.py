import time
from datetime import datetime
from uuid import UUID
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.search_enrichment import SearchEnrichmentService
from app.schemas.search import SearchResult


class SearchService:
    """Semantic search: Qdrant vectors + efficient batch enrichment."""

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStoreService | None = None,
    ):
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or VectorStoreService()
        self.enrichment = SearchEnrichmentService(db)

    async def search(
        self,
        query: str,
        limit: int = 10,
        speaker: str | None = None,
        channel_id: UUID | None = None,
        channel_slug: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_context: bool = True,
        context_utterances: int = 3,
    ) -> tuple[list[SearchResult], int]:
        """
        Semantic search with metadata filtering.

        Args:
            query: Search query text
            limit: Maximum number of results
            speaker: Filter by speaker name
            channel_id: Filter by channel ID
            channel_slug: Filter by channel slug (alternative to channel_id)
            date_from: Filter by minimum published date
            date_to: Filter by maximum published date
            include_context: Include surrounding utterances
            context_utterances: Number of utterances to include before/after

        Returns:
            Tuple of (results list, processing time in ms)
        """
        start_time = time.time()

        logger.info(f"Searching for: {query}")

        # Resolve channel_slug to channel_id if needed
        if channel_slug and not channel_id:
            channel = await self._get_channel_by_slug(channel_slug)
            if channel:
                channel_id = channel.id

        # Generate query embedding
        query_vector = await self.embedding_service.embed_query(query)

        # Search Qdrant
        vector_results = await self.vector_store.search(
            query_vector=query_vector,
            limit=limit,
            speaker=speaker,
            channel_id=str(channel_id) if channel_id else None,
            date_from=date_from,
            date_to=date_to,
        )

        if not vector_results:
            processing_time = int((time.time() - start_time) * 1000)
            return [], processing_time

        # Enrich results efficiently using batch loading (fixes N+1)
        results = await self.enrichment.enrich_results(
            vector_results,
            include_context=include_context,
            context_count=context_utterances,
        )

        processing_time = int((time.time() - start_time) * 1000)
        logger.info(f"Found {len(results)} results in {processing_time}ms")

        return results, processing_time

    async def search_by_speaker(
        self,
        speaker: str,
        query: str,
        limit: int = 10,
    ) -> tuple[list[SearchResult], int]:
        """Convenience method for speaker-specific search."""
        return await self.search(
            query=query,
            limit=limit,
            speaker=speaker,
        )

    async def _get_channel_by_slug(self, slug: str) -> Channel | None:
        """Get channel by slug."""
        result = await self.db.execute(select(Channel).where(Channel.slug == slug))
        return result.scalar_one_or_none()
