"""Hybrid search combining semantic and keyword search with re-ranking."""

import time
from datetime import datetime
from uuid import UUID
from typing import Optional
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.cache import CacheService, EmbeddingCache, SearchCache
from app.services.reranker import RerankerService
from app.services.postgres_search import PostgresSearchService
from app.services.search_enrichment import SearchEnrichmentService
from app.schemas.search import SearchResult


class HybridSearchService:
    """
    Hybrid search combining:
    1. Semantic search (Qdrant)
    2. Keyword search (BM25 / Postgres full-text)
    3. Re-ranking with cross-encoder
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService = None,
        vector_store: VectorStoreService = None,
        reranker: RerankerService = None,
        use_cache: bool = True,
    ):
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or VectorStoreService()
        self.reranker = reranker or RerankerService()
        self.use_cache = use_cache

        # New services for efficient search
        self.postgres_search = PostgresSearchService(db)
        self.enrichment = SearchEnrichmentService(db)

        if use_cache:
            self.cache = CacheService()
            self.embedding_cache = EmbeddingCache(self.cache)
            self.search_cache = SearchCache(self.cache)
        else:
            self.cache = None
            self.embedding_cache = None
            self.search_cache = None

    async def search(
        self,
        query: str,
        limit: int = 10,
        speaker: str = None,
        channel_id: UUID = None,
        channel_slug: str = None,
        date_from: datetime = None,
        date_to: datetime = None,
        include_context: bool = True,
        context_utterances: int = 3,
        use_reranking: bool = True,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> tuple[list[SearchResult], int]:
        """
        Hybrid search with semantic + keyword matching.

        Args:
            query: Search query
            limit: Number of results to return
            speaker: Filter by speaker name
            channel_id: Filter by channel
            channel_slug: Filter by channel slug
            date_from: Filter by min date
            date_to: Filter by max date
            include_context: Include surrounding utterances
            context_utterances: Number of context utterances
            use_reranking: Apply cross-encoder re-ranking
            semantic_weight: Weight for semantic search (0-1)
            keyword_weight: Weight for keyword search (0-1)

        Returns:
            Tuple of (results list, processing time in ms)
        """
        start_time = time.time()
        logger.info(f"Hybrid search: {query}")

        # Check cache first
        if self.search_cache:
            filters = {
                "speaker": speaker,
                "channel_id": str(channel_id) if channel_id else None,
                "channel_slug": channel_slug,
            }
            cached = await self.search_cache.get(query, filters, limit)
            if cached:
                logger.info("Search cache hit")
                processing_time = int((time.time() - start_time) * 1000)
                return [SearchResult(**r) for r in cached], processing_time

        # Resolve channel_slug to channel_id
        if channel_slug and not channel_id:
            channel = await self._get_channel_by_slug(channel_slug)
            if channel:
                channel_id = channel.id

        # Get candidate pool (3x limit for re-ranking)
        candidate_limit = limit * 3 if use_reranking else limit

        # Run semantic and keyword search in parallel
        semantic_results = await self._semantic_search(
            query=query,
            limit=candidate_limit,
            speaker=speaker,
            channel_id=channel_id,
            date_from=date_from,
            date_to=date_to,
        )

        keyword_results = await self._keyword_search(
            query=query,
            limit=candidate_limit,
            speaker=speaker,
            channel_id=channel_id,
        )

        # Combine with Reciprocal Rank Fusion
        combined = self._reciprocal_rank_fusion(
            semantic_results,
            keyword_results,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

        logger.info(
            f"Combined {len(semantic_results)} semantic + {len(keyword_results)} keyword = {len(combined)} candidates"
        )

        # Apply MMR diversity to prevent redundant results from same minute
        # Do this before reranking to ensure diverse candidates
        combined = self._apply_mmr_diversity(combined, lambda_param=0.7)

        # Re-rank with cross-encoder (increased pool size for better quality)
        if use_reranking and combined:
            # Rerank top 50 candidates for better quality
            rerank_pool = min(50, len(combined))
            combined = await self.reranker.rerank(
                query, combined[:rerank_pool], top_k=limit
            )
        else:
            combined = combined[:limit]

        # Enrich results efficiently using batch loading (fixes N+1)
        results = await self.enrichment.enrich_results(
            combined,
            include_context=include_context,
            context_count=context_utterances,
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Cache results
        if self.search_cache:
            filters = {
                "speaker": speaker,
                "channel_id": str(channel_id) if channel_id else None,
                "channel_slug": channel_slug,
            }
            await self.search_cache.set(
                query,
                [r.model_dump() for r in results],
                filters,
                limit,
            )

        logger.info(f"Found {len(results)} results in {processing_time}ms")
        return results, processing_time

    async def _semantic_search(
        self,
        query: str,
        limit: int,
        speaker: str = None,
        channel_id: UUID = None,
        date_from: datetime = None,
        date_to: datetime = None,
    ) -> list[dict]:
        """Semantic search using Qdrant."""
        # Get query embedding (with caching)
        if self.embedding_cache:
            query_vector = await self.embedding_cache.get(query)
            if not query_vector:
                query_vector = await self.embedding_service.embed_query(query)
                await self.embedding_cache.set(query, query_vector)
        else:
            query_vector = await self.embedding_service.embed_query(query)

        # Search Qdrant
        results = await self.vector_store.search(
            query_vector=query_vector,
            limit=limit,
            speaker=speaker,
            channel_id=str(channel_id) if channel_id else None,
            date_from=date_from,
            date_to=date_to,
            score_threshold=0.2,  # Lower threshold for hybrid
        )

        return results

    async def _keyword_search(
        self,
        query: str,
        limit: int,
        speaker: str = None,
        channel_id: UUID = None,
    ) -> list[dict]:
        """
        Keyword search using PostgreSQL full-text search.

        Uses GIN indexes for O(log n) lookups instead of O(n) in-memory BM25.
        This is much more efficient for large datasets.
        """
        # Use PostgreSQL FTS instead of in-memory BM25
        keyword_results = await self.postgres_search.keyword_search(
            query=query,
            limit=limit,
            channel_id=channel_id,
            speaker=speaker,
        )

        # Convert to dict format matching semantic results
        results = []
        for result in keyword_results:
            results.append(
                {
                    "id": str(result.chunk_id),
                    "chunk_id": str(result.chunk_id),
                    "episode_id": str(result.episode_id),
                    "channel_id": str(result.channel_id),
                    "text": result.text,
                    "speaker": result.primary_speaker,
                    "speakers": result.speakers,
                    "start_ms": result.start_ms,
                    "end_ms": result.end_ms,
                    "score": result.rank,  # ts_rank score (already 0-1 range)
                    "search_type": "keyword",
                }
            )

        return results

    def _reciprocal_rank_fusion(
        self,
        semantic_results: list[dict],
        keyword_results: list[dict],
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        k: int = 60,
    ) -> list[dict]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).

        RRF score = sum(weight / (k + rank)) for each result list
        """
        scores = {}
        results_map = {}

        # Process semantic results
        for rank, result in enumerate(semantic_results, 1):
            doc_id = result.get("chunk_id") or result.get("id")
            if doc_id not in scores:
                scores[doc_id] = 0
                results_map[doc_id] = result
            scores[doc_id] += semantic_weight / (k + rank)
            results_map[doc_id]["semantic_rank"] = rank
            results_map[doc_id]["semantic_score"] = result.get("score", 0)

        # Process keyword results
        for rank, result in enumerate(keyword_results, 1):
            doc_id = result.get("chunk_id") or result.get("id")
            if doc_id not in scores:
                scores[doc_id] = 0
                results_map[doc_id] = result
            scores[doc_id] += keyword_weight / (k + rank)
            results_map[doc_id]["keyword_rank"] = rank
            results_map[doc_id]["keyword_score"] = result.get("score", 0)

        # Sort by combined score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # Build final results
        combined = []
        for doc_id in sorted_ids:
            result = results_map[doc_id].copy()
            result["rrf_score"] = scores[doc_id]
            result["score"] = scores[doc_id]  # Use RRF score as primary
            combined.append(result)

        return combined

    def _apply_mmr_diversity(
        self,
        results: list[dict],
        lambda_param: float = 0.7,
        time_window_ms: int = 60000,  # 1 minute
    ) -> list[dict]:
        """
        Apply Maximal Marginal Relevance (MMR) to diversify results.

        Prevents 5 results from the same minute of the same episode.
        Balances relevance with diversity.

        Args:
            results: Ranked search results
            lambda_param: Balance between relevance (1.0) and diversity (0.0)
            time_window_ms: Time window to consider as "same segment"

        Returns:
            Diversified results
        """
        if not results or len(results) <= 1:
            return results

        selected = [results[0]]  # Always include top result
        remaining = results[1:]

        while remaining and len(selected) < len(results):
            best_idx = 0
            best_score = float("-inf")

            for i, candidate in enumerate(remaining):
                # Relevance score (from RRF)
                relevance = candidate.get("score", 0)

                # Diversity penalty: check overlap with selected results
                max_similarity = 0
                for sel in selected:
                    similarity = self._compute_temporal_similarity(
                        candidate, sel, time_window_ms
                    )
                    max_similarity = max(max_similarity, similarity)

                # MMR score: balance relevance with diversity
                mmr_score = (
                    lambda_param * relevance - (1 - lambda_param) * max_similarity
                )

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    def _compute_temporal_similarity(
        self,
        result1: dict,
        result2: dict,
        time_window_ms: int,
    ) -> float:
        """
        Compute similarity based on temporal/episode overlap.

        Returns 1.0 if same episode and within time window, 0.0 otherwise.
        """
        # Different episodes = no similarity
        if result1.get("episode_id") != result2.get("episode_id"):
            return 0.0

        # Same episode - check time overlap
        start1 = result1.get("start_ms", 0)
        start2 = result2.get("start_ms", 0)

        time_diff = abs(start1 - start2)

        if time_diff < time_window_ms:
            # High similarity if within 1 minute
            return 1.0 - (time_diff / time_window_ms)

        return 0.0

    async def _get_channel_by_slug(self, slug: str) -> Optional[Channel]:
        """Get channel by slug."""
        result = await self.db.execute(select(Channel).where(Channel.slug == slug))
        return result.scalar_one_or_none()
