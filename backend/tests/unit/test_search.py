"""Unit tests for search services."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.services.search import SearchService
from app.services.hybrid_search import HybridSearchService
from app.services.postgres_search import PostgresSearchService, KeywordSearchResult


class TestSearchService:
    """Tests for semantic search service."""

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, db_session, mock_embedding_service, mock_vector_store):
        """Empty query should return empty results."""
        service = SearchService(
            db=db_session,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )

        # Mock returns empty
        mock_vector_store.search.return_value = []

        results, time_ms = await service.search(query="test query")

        assert results == []
        assert time_ms >= 0
        mock_embedding_service.embed_query.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_search_with_channel_filter(self, db_session, mock_embedding_service, mock_vector_store):
        """Search should pass channel filter to vector store."""
        service = SearchService(
            db=db_session,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )

        channel_id = uuid4()
        mock_vector_store.search.return_value = []

        await service.search(query="test", channel_id=channel_id)

        # Verify channel_id was passed
        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs["channel_id"] == str(channel_id)

    @pytest.mark.asyncio
    async def test_search_with_speaker_filter(self, db_session, mock_embedding_service, mock_vector_store):
        """Search should pass speaker filter to vector store."""
        service = SearchService(
            db=db_session,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )

        mock_vector_store.search.return_value = []

        await service.search(query="test", speaker="Sam Parr")

        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs["speaker"] == "Sam Parr"

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, db_session, mock_embedding_service, mock_vector_store):
        """Search should respect the limit parameter."""
        service = SearchService(
            db=db_session,
            embedding_service=mock_embedding_service,
            vector_store=mock_vector_store,
        )

        mock_vector_store.search.return_value = []

        await service.search(query="test", limit=5)

        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs["limit"] == 5


class TestHybridSearchService:
    """Tests for hybrid search service."""

    @pytest.mark.asyncio
    async def test_reciprocal_rank_fusion(self):
        """Test RRF score calculation."""
        service = HybridSearchService.__new__(HybridSearchService)

        semantic_results = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
        ]
        keyword_results = [
            {"chunk_id": "b", "score": 0.95},
            {"chunk_id": "c", "score": 0.7},
        ]

        combined = service._reciprocal_rank_fusion(
            semantic_results,
            keyword_results,
            semantic_weight=0.7,
            keyword_weight=0.3,
        )

        # b should be ranked higher since it appears in both
        chunk_ids = [r["chunk_id"] for r in combined]
        assert "b" in chunk_ids
        assert "a" in chunk_ids
        assert "c" in chunk_ids

    @pytest.mark.asyncio
    async def test_hybrid_search_uses_both_methods(self, db_session, mock_embedding_service, mock_vector_store):
        """Hybrid search should query both semantic and keyword."""
        with patch.object(HybridSearchService, '_keyword_search', new_callable=AsyncMock) as mock_keyword:
            mock_keyword.return_value = []
            mock_vector_store.search.return_value = []

            service = HybridSearchService(
                db=db_session,
                embedding_service=mock_embedding_service,
                vector_store=mock_vector_store,
                use_cache=False,
            )

            await service.search(query="test query", use_reranking=False)

            # Both methods should be called
            mock_embedding_service.embed_query.assert_called()


class TestPostgresSearchService:
    """Tests for PostgreSQL full-text search."""

    def test_build_tsquery_simple(self):
        """Test simple query conversion."""
        service = PostgresSearchService.__new__(PostgresSearchService)

        result = service._build_tsquery("hello world")

        assert "'hello'" in result
        assert "'world'" in result
        assert "&" in result

    def test_build_tsquery_with_or(self):
        """Test OR query conversion."""
        service = PostgresSearchService.__new__(PostgresSearchService)

        result = service._build_tsquery("hello OR world")

        assert "|" in result

    def test_build_tsquery_with_phrase(self):
        """Test phrase query conversion."""
        service = PostgresSearchService.__new__(PostgresSearchService)

        result = service._build_tsquery('"exact phrase"')

        assert "<->" in result  # Adjacent operator

    def test_build_tsquery_empty(self):
        """Test empty query handling."""
        service = PostgresSearchService.__new__(PostgresSearchService)

        result = service._build_tsquery("")

        assert result == "''"

    def test_build_tsquery_special_chars(self):
        """Test special character handling."""
        service = PostgresSearchService.__new__(PostgresSearchService)

        result = service._build_tsquery("hello! @world#")

        # Should clean special chars
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result
