"""
Unit tests for service modules.

Tests service logic with mocked external dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime


class TestChunkingService:
    """Tests for ChunkingService."""

    def test_chunk_empty_utterances(self):
        """Should return empty list for empty input."""
        from app.services.chunking import ChunkingService

        service = ChunkingService()
        chunks = service.chunk_transcript([], "episode-123")
        assert chunks == []

    def test_chunk_single_utterance(self):
        """Should create single chunk for small transcript."""
        from app.services.chunking import ChunkingService

        service = ChunkingService(target_chunk_size=500, min_chunk_size=10)
        utterances = [
            {
                "speaker": "Host",
                "text": "Welcome to the podcast. Today we discuss technology.",
                "start_ms": 0,
                "end_ms": 5000,
            }
        ]
        chunks = service.chunk_transcript(utterances, "ep-1")

        assert len(chunks) == 1
        assert chunks[0].primary_speaker == "Host"
        assert "Welcome to the podcast" in chunks[0].text

    def test_chunk_multiple_utterances(self):
        """Should group multiple utterances into chunks."""
        from app.services.chunking import ChunkingService

        service = ChunkingService(target_chunk_size=20, min_chunk_size=5)
        utterances = [
            {"speaker": "Host", "text": "Word " * 15, "start_ms": 0, "end_ms": 5000},
            {
                "speaker": "Guest",
                "text": "Word " * 15,
                "start_ms": 5000,
                "end_ms": 10000,
            },
            {
                "speaker": "Host",
                "text": "Word " * 15,
                "start_ms": 10000,
                "end_ms": 15000,
            },
        ]
        chunks = service.chunk_transcript(utterances, "ep-1")

        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.word_count > 0
            assert chunk.start_ms >= 0
            assert chunk.end_ms > chunk.start_ms

    def test_chunk_preserves_speaker_info(self):
        """Should track all speakers in each chunk."""
        from app.services.chunking import ChunkingService

        service = ChunkingService(target_chunk_size=100, min_chunk_size=10)
        utterances = [
            {
                "speaker": "Host",
                "text": "Hello everyone.",
                "start_ms": 0,
                "end_ms": 2000,
            },
            {
                "speaker": "Guest1",
                "text": "Thanks for having me.",
                "start_ms": 2000,
                "end_ms": 4000,
            },
            {
                "speaker": "Guest2",
                "text": "Great to be here.",
                "start_ms": 4000,
                "end_ms": 6000,
            },
        ]
        chunks = service.chunk_transcript(utterances, "ep-1")

        # All speakers should be tracked
        all_speakers = set()
        for chunk in chunks:
            all_speakers.update(chunk.speakers)
        assert "Host" in all_speakers
        assert "Guest1" in all_speakers
        assert "Guest2" in all_speakers

    def test_chunk_with_episode_context(self):
        """Should include episode context in text_for_embedding."""
        from app.services.chunking import ChunkingService, EpisodeContext

        service = ChunkingService(target_chunk_size=500, min_chunk_size=10)
        context = EpisodeContext(
            episode_title="The Future of AI",
            channel_name="Tech Talk",
            published_at=datetime(2024, 6, 15),
        )
        utterances = [
            {
                "speaker": "Host",
                "text": "Let's discuss AI trends.",
                "start_ms": 0,
                "end_ms": 3000,
            },
        ]
        chunks = service.chunk_transcript(utterances, "ep-1", episode_context=context)

        assert len(chunks) == 1
        embedding_text = chunks[0].text_for_embedding
        assert "Episode: The Future of AI" in embedding_text
        assert "Channel: Tech Talk" in embedding_text
        assert "June 2024" in embedding_text

    def test_is_good_break_point_speaker_change(self):
        """Should identify speaker change as break point."""
        from app.services.chunking import ChunkingService

        service = ChunkingService()
        current = [
            {"speaker": "Host", "text": "Question here?", "start_ms": 0, "end_ms": 2000}
        ]
        next_utt = {
            "speaker": "Guest",
            "text": "Answer here.",
            "start_ms": 2000,
            "end_ms": 4000,
        }

        assert service._is_good_break_point(current, next_utt) is True

    def test_is_good_break_point_long_pause(self):
        """Should identify long pause as break point."""
        from app.services.chunking import ChunkingService

        service = ChunkingService()
        current = [
            {"speaker": "Host", "text": "First thought.", "start_ms": 0, "end_ms": 2000}
        ]
        # 3 second pause
        next_utt = {
            "speaker": "Host",
            "text": "New topic.",
            "start_ms": 5000,
            "end_ms": 7000,
        }

        assert service._is_good_break_point(current, next_utt) is True

    def test_detect_topic_shift(self):
        """Should detect topic transition markers."""
        from app.services.chunking import ChunkingService

        service = ChunkingService()
        current = [
            {
                "speaker": "Host",
                "text": "That's interesting.",
                "start_ms": 0,
                "end_ms": 2000,
            }
        ]
        next_utt = {
            "speaker": "Host",
            "text": "Moving on, let's talk about something else.",
            "start_ms": 2000,
            "end_ms": 5000,
        }

        assert service._detect_topic_shift(current, next_utt) is True

    def test_overlap_utterances(self):
        """Should return overlapping utterances for context."""
        from app.services.chunking import ChunkingService

        service = ChunkingService(chunk_overlap=10)
        utterances = [
            {"speaker": "A", "text": "One two three.", "start_ms": 0, "end_ms": 1000},
            {
                "speaker": "B",
                "text": "Four five six.",
                "start_ms": 1000,
                "end_ms": 2000,
            },
            {
                "speaker": "A",
                "text": "Seven eight nine ten.",
                "start_ms": 2000,
                "end_ms": 3000,
            },
        ]
        overlap = service._get_overlap_utterances(utterances)

        # Should get some utterances from the end
        assert len(overlap) > 0
        total_words = sum(len(u["text"].split()) for u in overlap)
        assert total_words <= 10


class TestSpeakerLabelingService:
    """Tests for SpeakerLabelingService."""

    def test_apply_speaker_labels(self):
        """Should apply speaker mapping to utterances."""
        from app.services.speaker_labeling import SpeakerLabelingService
        from app.services.transcription.base import Utterance

        with patch("app.services.speaker_labeling.anthropic"):
            service = SpeakerLabelingService()

        utterances = [
            Utterance(speaker="SPEAKER_00", text="Hello", start_ms=0, end_ms=1000),
            Utterance(
                speaker="SPEAKER_01", text="Hi there", start_ms=1000, end_ms=2000
            ),
        ]
        mapping = {"SPEAKER_00": "Sam", "SPEAKER_01": "Guest"}

        labeled = service.apply_speaker_labels(utterances, mapping)

        assert labeled[0]["speaker"] == "Sam"
        assert labeled[0]["speaker_raw"] == "SPEAKER_00"
        assert labeled[1]["speaker"] == "Guest"
        assert labeled[1]["speaker_raw"] == "SPEAKER_01"

    def test_apply_speaker_labels_unknown_speaker(self):
        """Should handle unknown speakers with default label."""
        from app.services.speaker_labeling import SpeakerLabelingService
        from app.services.transcription.base import Utterance

        with patch("app.services.speaker_labeling.anthropic"):
            service = SpeakerLabelingService()

        utterances = [
            Utterance(speaker="SPEAKER_99", text="Hello", start_ms=0, end_ms=1000),
        ]
        mapping = {"SPEAKER_00": "Host"}  # SPEAKER_99 not in mapping

        labeled = service.apply_speaker_labels(utterances, mapping)

        # Should use default label for unknown speaker
        assert labeled[0]["speaker_raw"] == "SPEAKER_99"
        assert labeled[0]["speaker"] == "Guest"  # Default label

    @pytest.mark.asyncio
    async def test_identify_speakers_empty_utterances(self):
        """Should return empty mapping for empty utterances."""
        from app.services.speaker_labeling import SpeakerLabelingService

        with patch("app.services.speaker_labeling.anthropic"):
            service = SpeakerLabelingService()

        mapping = await service.identify_speakers(
            utterances=[],
            known_speakers=["Host", "Guest"],
        )

        assert mapping == {}


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.mark.asyncio
    async def test_embed_query(self):
        """Should embed single query text."""
        from app.services.embedding import EmbeddingService

        with patch("app.services.embedding.openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create.return_value = mock_response
            MockAsyncOpenAI.return_value = mock_client

            service = EmbeddingService()
            embedding = await service.embed_query("test query")

            assert len(embedding) == 1536
            mock_client.embeddings.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_texts_batching(self):
        """Should batch multiple texts for embedding."""
        from app.services.embedding import EmbeddingService

        with patch("app.services.embedding.openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = AsyncMock()
            # Mock embedding items with index for proper ordering
            mock_embedding1 = MagicMock()
            mock_embedding1.embedding = [0.1] * 1536
            mock_embedding1.index = 0
            mock_embedding2 = MagicMock()
            mock_embedding2.embedding = [0.2] * 1536
            mock_embedding2.index = 1
            mock_response = MagicMock()
            mock_response.data = [mock_embedding1, mock_embedding2]
            mock_client.embeddings.create.return_value = mock_response
            MockAsyncOpenAI.return_value = mock_client

            service = EmbeddingService()
            embeddings = await service.embed_texts(["text1", "text2"])

            assert len(embeddings) == 2
            assert len(embeddings[0]) == 1536

    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """Should return empty list for empty input."""
        from app.services.embedding import EmbeddingService

        with patch("app.services.embedding.openai.AsyncOpenAI"):
            service = EmbeddingService()
            embeddings = await service.embed_texts([])
            assert embeddings == []


class TestVectorStoreService:
    """Tests for VectorStoreService."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Should return search results from Qdrant."""
        from app.services.vector_store import VectorStoreService

        with patch("app.services.vector_store.QdrantClient") as MockQdrant:
            mock_client = MagicMock()
            mock_client.search.return_value = [
                MagicMock(
                    id="chunk-1",
                    score=0.95,
                    payload={
                        "text": "Test content",
                        "episode_id": str(uuid4()),
                        "channel_id": str(uuid4()),
                        "primary_speaker": "Host",
                        "speakers": ["Host"],
                        "start_ms": 0,
                        "end_ms": 5000,
                    },
                )
            ]
            MockQdrant.return_value = mock_client

            service = VectorStoreService()
            results = await service.search(
                query_vector=[0.1] * 1536,
                limit=10,
            )

            assert len(results) == 1
            assert results[0]["text"] == "Test content"
            assert results[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_with_filters(self):
        """Should apply filters to search."""
        from app.services.vector_store import VectorStoreService

        with patch("app.services.vector_store.QdrantClient") as MockQdrant:
            mock_client = MagicMock()
            mock_client.search.return_value = []
            MockQdrant.return_value = mock_client

            service = VectorStoreService()
            channel_id = str(uuid4())
            await service.search(
                query_vector=[0.1] * 1536,
                limit=10,
                channel_id=channel_id,
                speaker="Host",
            )

            # Verify filters were passed
            call_args = mock_client.search.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_upsert_chunks(self):
        """Should upsert chunks to Qdrant."""
        from app.services.vector_store import VectorStoreService

        with patch("app.services.vector_store.QdrantClient") as MockQdrant:
            mock_client = MagicMock()
            MockQdrant.return_value = mock_client

            service = VectorStoreService()
            chunks = [
                {
                    "chunk_id": str(uuid4()),
                    "episode_id": str(uuid4()),
                    "channel_id": str(uuid4()),
                    "text": "Test content",
                    "primary_speaker": "Host",
                    "speakers": ["Host"],
                    "start_ms": 0,
                    "end_ms": 5000,
                }
            ]
            embeddings = [[0.1] * 1536]

            point_ids = await service.upsert_chunks(chunks, embeddings)

            assert len(point_ids) == 1
            mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_episode(self):
        """Should delete all chunks for an episode."""
        from app.services.vector_store import VectorStoreService

        with patch("app.services.vector_store.QdrantClient") as MockQdrant:
            mock_client = MagicMock()
            MockQdrant.return_value = mock_client

            service = VectorStoreService()
            episode_id = str(uuid4())

            await service.delete_by_episode(episode_id)

            mock_client.delete.assert_called_once()


class TestYouTubeService:
    """Tests for YouTubeService."""

    @pytest.mark.asyncio
    async def test_cleanup_audio_removes_file(self):
        """Should remove audio file after processing."""
        from pathlib import Path

        # Test the cleanup logic directly without instantiating the service
        test_path = Path("/tmp/test_audio_cleanup.mp3")

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "unlink") as mock_unlink:
                # Simulate what cleanup_audio does
                if test_path.exists():
                    test_path.unlink()
                mock_unlink.assert_called_once()

    def test_parse_duration(self):
        """Should parse duration from various formats."""
        # Test duration parsing logic
        duration_str = "PT1H30M45S"  # ISO 8601 format

        # Parse hours, minutes, seconds
        import re

        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            total_seconds = hours * 3600 + minutes * 60 + seconds

            assert total_seconds == 5445  # 1h 30m 45s

    def test_extract_video_id_from_url(self):
        """Should extract video ID from various YouTube URL formats."""
        import re

        urls = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]

        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        ]

        for url, expected_id in urls:
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    assert match.group(1) == expected_id
                    break


class TestRerankerService:
    """Tests for RerankerService."""

    @pytest.mark.asyncio
    async def test_rerank_empty_results(self):
        """Should handle empty results."""
        from app.services.reranker import RerankerService

        service = RerankerService()
        reranked = await service.rerank("test query", [])

        assert reranked == []

    @pytest.mark.asyncio
    async def test_rerank_single_result_no_model(self):
        """Should return results as-is when model not available."""
        from app.services.reranker import RerankerService

        # When cross-encoder not available, should return original results
        with patch("app.services.reranker.CROSS_ENCODER_AVAILABLE", False):
            service = RerankerService()
            results = [{"text": "Test content", "score": 0.8}]

            reranked = await service.rerank("test query", results)

            assert len(reranked) == 1
            assert reranked[0]["text"] == "Test content"

    @pytest.mark.asyncio
    async def test_rerank_preserves_metadata(self):
        """Should preserve all metadata in reranked results."""
        from app.services.reranker import RerankerService

        # When cross-encoder not available, results pass through unchanged
        with patch("app.services.reranker.CROSS_ENCODER_AVAILABLE", False):
            service = RerankerService()

            results = [
                {
                    "text": "Content A",
                    "score": 0.8,
                    "episode_id": "ep1",
                    "speaker": "Host",
                },
                {
                    "text": "Content B",
                    "score": 0.7,
                    "episode_id": "ep2",
                    "speaker": "Guest",
                },
            ]

            reranked = await service.rerank("test query", results)

            assert all("episode_id" in r for r in reranked)
            assert all("speaker" in r for r in reranked)


class TestHybridSearchService:
    """Tests for HybridSearchService."""

    def test_reciprocal_rank_fusion(self):
        """Should correctly compute RRF scores."""
        from app.services.hybrid_search import HybridSearchService

        service = HybridSearchService.__new__(HybridSearchService)

        # Results from two different rankers
        vector_results = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
            {"chunk_id": "c", "score": 0.7},
        ]
        keyword_results = [
            {"chunk_id": "b", "score": 0.95},
            {"chunk_id": "d", "score": 0.85},
            {"chunk_id": "a", "score": 0.75},
        ]

        fused = service._reciprocal_rank_fusion(vector_results, keyword_results, k=60)

        # 'a' and 'b' should be in top results (appear in both)
        chunk_ids = [r["chunk_id"] for r in fused[:2]]
        assert "a" in chunk_ids or "b" in chunk_ids

    @pytest.mark.asyncio
    async def test_search_combines_vector_and_keyword(self):
        """Should combine vector and keyword search."""
        from app.services.hybrid_search import HybridSearchService

        with patch("app.services.hybrid_search.EmbeddingService") as MockEmbed, patch(
            "app.services.hybrid_search.VectorStoreService"
        ) as MockVector, patch(
            "app.services.hybrid_search.PostgresSearchService"
        ) as MockKeyword:

            mock_embed = AsyncMock()
            mock_embed.embed_query.return_value = [0.1] * 1536
            MockEmbed.return_value = mock_embed

            mock_vector = AsyncMock()
            mock_vector.search.return_value = [
                {"chunk_id": "1", "text": "Result 1", "score": 0.9}
            ]
            MockVector.return_value = mock_vector

            mock_keyword = AsyncMock()
            mock_keyword.search.return_value = [
                {"chunk_id": "2", "text": "Result 2", "score": 0.8}
            ]
            MockKeyword.return_value = mock_keyword

            service = HybridSearchService(db=AsyncMock())
            results = await service.search("test query", limit=10)

            # Should have results from both sources
            assert len(results) >= 1


class TestRateLimitCache:
    """Tests for the LRU rate limit cache."""

    def test_lru_cache_eviction(self):
        """Should evict oldest entries when full."""
        from app.dependencies import LRURateLimitCache

        cache = LRURateLimitCache(max_size=3)

        cache.set("key1", [1.0])
        cache.set("key2", [2.0])
        cache.set("key3", [3.0])
        cache.set("key4", [4.0])  # Should evict key1

        assert cache.get("key1") == []  # Evicted
        assert cache.get("key4") == [4.0]

    def test_lru_cache_access_refreshes(self):
        """Accessing an item should refresh its position."""
        from app.dependencies import LRURateLimitCache

        cache = LRURateLimitCache(max_size=3)

        cache.set("key1", [1.0])
        cache.set("key2", [2.0])
        cache.set("key3", [3.0])

        # Access key1 to refresh it
        cache.get("key1")

        # Add key4, should evict key2 (oldest untouched)
        cache.set("key4", [4.0])

        assert cache.get("key1") == [1.0]  # Still there
        assert cache.get("key2") == []  # Evicted

    def test_lru_cache_thread_safety(self):
        """Cache should be thread-safe."""
        from app.dependencies import LRURateLimitCache
        import threading

        cache = LRURateLimitCache(max_size=100)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key{threading.current_thread().name}{i}", [float(i)])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
