"""
Integration tests for the transcription pipeline.

Uses mocks for external services (YouTube, transcription, embeddings).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from pathlib import Path

from app.workers.pipeline import TranscriptionPipeline
from app.services.transcription.base import TranscriptResult, TranscriptionStatus


@pytest.fixture
def mock_youtube_service():
    """Mock YouTube service."""
    mock = AsyncMock()
    mock.download_audio.return_value = Path("/tmp/test_audio.mp3")
    mock.cleanup_audio.return_value = None
    return mock


@pytest.fixture
def mock_transcription_provider():
    """Mock transcription provider."""
    mock = AsyncMock()
    mock.transcribe.return_value = TranscriptResult(
        provider_job_id="test-job-123",
        status=TranscriptionStatus.COMPLETED,
        utterances=[
            {
                "speaker": "SPEAKER_00",
                "text": "Hello, welcome to the podcast.",
                "start_ms": 0,
                "end_ms": 3000,
                "confidence": 0.95,
            },
            {
                "speaker": "SPEAKER_01",
                "text": "Thanks for having me on the show.",
                "start_ms": 3000,
                "end_ms": 6000,
                "confidence": 0.92,
            },
            {
                "speaker": "SPEAKER_00",
                "text": "Today we're going to talk about technology and startups.",
                "start_ms": 6000,
                "end_ms": 10000,
                "confidence": 0.98,
            },
        ],
        raw_response={"test": "data"},
        duration_ms=120000,
        cost_cents=5,
    )
    return mock


@pytest.fixture
def mock_speaker_labeling():
    """Mock speaker labeling service."""
    mock = MagicMock()
    # identify_speakers is async, so use AsyncMock for it
    mock.identify_speakers = AsyncMock(
        return_value={
            "SPEAKER_00": "Host",
            "SPEAKER_01": "Guest",
        }
    )
    # apply_speaker_labels is sync, so use regular return_value
    mock.apply_speaker_labels.return_value = [
        {
            "speaker": "Host",
            "speaker_raw": "SPEAKER_00",
            "text": "Hello, welcome to the podcast.",
            "start_ms": 0,
            "end_ms": 3000,
            "confidence": 0.95,
        },
        {
            "speaker": "Guest",
            "speaker_raw": "SPEAKER_01",
            "text": "Thanks for having me on the show.",
            "start_ms": 3000,
            "end_ms": 6000,
            "confidence": 0.92,
        },
        {
            "speaker": "Host",
            "speaker_raw": "SPEAKER_00",
            "text": "Today we're going to talk about technology and startups.",
            "start_ms": 6000,
            "end_ms": 10000,
            "confidence": 0.98,
        },
    ]
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    mock = AsyncMock()
    # Return fixed embeddings
    mock.embed_texts.return_value = [[0.1] * 1536]
    mock.embed_query.return_value = [0.1] * 1536
    return mock


@pytest.fixture
def mock_vector_store():
    """Mock vector store."""
    mock = AsyncMock()
    mock.upsert_chunks.return_value = [str(uuid4())]
    mock.ensure_collection.return_value = None
    return mock


class TestTranscriptionPipeline:
    """Tests for the full transcription pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_processes_episode_successfully(
        self,
        db_session,
        mock_youtube_service,
        mock_transcription_provider,
        mock_speaker_labeling,
        mock_embedding_service,
        mock_vector_store,
    ):
        """Pipeline should process an episode through all stages."""
        from app.models import Channel, Episode, Job, Batch

        # Create test data
        channel = Channel(
            id=uuid4(),
            slug="test-channel",
            name="Test Channel",
            youtube_channel_id="UC123",
            speakers=["Host", "Guest"],
        )
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="test123",
            title="Test Episode",
            status="pending",
        )
        db_session.add(episode)

        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Test Batch",
            provider="mock",
            status="running",
            total_episodes=1,
        )
        db_session.add(batch)

        job = Job(
            id=uuid4(),
            batch_id=batch.id,
            episode_id=episode.id,
            provider="mock",
            status="pending",
        )
        db_session.add(job)
        await db_session.commit()

        # Create pipeline with mocks
        with patch(
            "app.workers.pipeline.YouTubeService", return_value=mock_youtube_service
        ), patch(
            "app.workers.pipeline.get_provider",
            return_value=mock_transcription_provider,
        ), patch(
            "app.workers.pipeline.SpeakerLabelingService",
            return_value=mock_speaker_labeling,
        ), patch(
            "app.workers.pipeline.EmbeddingService", return_value=mock_embedding_service
        ), patch(
            "app.workers.pipeline.VectorStoreService", return_value=mock_vector_store
        ), patch(
            "app.workers.pipeline.settings"
        ) as mock_settings:

            # Configure mock settings
            mock_settings.TRANSCRIPTS_DIR = "/tmp/test_transcripts"

            pipeline = TranscriptionPipeline(
                db=db_session,
                provider_name="mock",
                speakers=["Host", "Guest"],
            )

            # Override mocked services
            pipeline.youtube = mock_youtube_service
            pipeline.speaker_labeling = mock_speaker_labeling
            pipeline.embedding = mock_embedding_service
            pipeline.vector_store = mock_vector_store

            # Run pipeline
            result = await pipeline.process_episode(
                job_id=job.id,
                episode_id=episode.id,
            )

        # Verify result
        assert result is True

        # Verify episode status updated
        await db_session.refresh(episode)
        assert episode.status == "done"

        # Verify job completed
        await db_session.refresh(job)
        assert job.status == "done"

        # Verify mocks called
        mock_youtube_service.download_audio.assert_called_once()
        mock_youtube_service.cleanup_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_handles_transcription_failure(
        self,
        db_session,
        mock_youtube_service,
        mock_embedding_service,
        mock_vector_store,
    ):
        """Pipeline should handle transcription failures gracefully."""
        from app.models import Channel, Episode, Job, Batch

        # Create test data
        channel = Channel(
            id=uuid4(),
            slug="test-channel-fail",
            name="Test Channel",
            youtube_channel_id="UC456",
        )
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="fail123",
            title="Failing Episode",
            status="pending",
        )
        db_session.add(episode)

        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Test Batch",
            provider="mock",
            status="running",
            total_episodes=1,
        )
        db_session.add(batch)

        job = Job(
            id=uuid4(),
            batch_id=batch.id,
            episode_id=episode.id,
            provider="mock",
            status="pending",
        )
        db_session.add(job)
        await db_session.commit()

        # Create failing transcription provider
        mock_failing_provider = AsyncMock()
        mock_failing_provider.transcribe.return_value = TranscriptResult(
            provider_job_id="failed-job-123",
            status=TranscriptionStatus.FAILED,
            error_message="API rate limit exceeded",
        )

        with patch(
            "app.workers.pipeline.YouTubeService", return_value=mock_youtube_service
        ), patch(
            "app.workers.pipeline.get_provider", return_value=mock_failing_provider
        ):

            pipeline = TranscriptionPipeline(
                db=db_session,
                provider_name="mock",
            )
            pipeline.youtube = mock_youtube_service

            # Run pipeline
            result = await pipeline.process_episode(
                job_id=job.id,
                episode_id=episode.id,
            )

        # Should return False on failure
        assert result is False

        # Verify episode marked as failed
        await db_session.refresh(episode)
        assert episode.status == "failed"

        # Verify job marked as failed with error
        await db_session.refresh(job)
        assert job.status == "failed"
        assert "API rate limit" in (job.error_message or "")


class TestChunkingIntegration:
    """Tests for chunking service integration."""

    @pytest.mark.asyncio
    async def test_chunking_creates_correct_chunks(self):
        """Chunking should create properly sized chunks."""
        from app.services.chunking import ChunkingService

        service = ChunkingService(
            target_chunk_size=10, chunk_overlap=2, min_chunk_size=5
        )

        # Create test utterances (10 words each)
        utterances = [
            {
                "speaker": "Host",
                "text": "One two three four five six seven eight nine ten.",
                "start_ms": 0,
                "end_ms": 5000,
            },
            {
                "speaker": "Guest",
                "text": "Eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty.",
                "start_ms": 5000,
                "end_ms": 10000,
            },
            {
                "speaker": "Host",
                "text": "Twenty-one twenty-two twenty-three twenty-four twenty-five.",
                "start_ms": 10000,
                "end_ms": 15000,
            },
        ]

        chunks = service.chunk_transcript(utterances, "test-episode-id")

        # Should create chunks
        assert len(chunks) >= 1

        # Each chunk should have required fields
        for chunk in chunks:
            assert hasattr(chunk, "text")
            assert hasattr(chunk, "primary_speaker")
            assert hasattr(chunk, "start_ms")
            assert hasattr(chunk, "end_ms")
            assert hasattr(chunk, "word_count")


class TestSearchEnrichmentIntegration:
    """Tests for search enrichment integration."""

    @pytest.mark.asyncio
    async def test_enrichment_batch_loads_entities(self, db_session):
        """Enrichment should batch load episodes and channels."""
        from app.models import Channel, Episode
        from app.services.search_enrichment import SearchEnrichmentService

        # Create test data
        channel = Channel(
            id=uuid4(),
            slug="enrich-test",
            name="Enrichment Test Channel",
            youtube_channel_id="UC789",
        )
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="enrich123",
            title="Enrichment Test Episode",
            status="done",
        )
        db_session.add(episode)
        await db_session.commit()

        # Create enrichment service
        service = SearchEnrichmentService(db_session)

        # Create mock vector results
        vector_results = [
            {
                "chunk_id": str(uuid4()),
                "episode_id": str(episode.id),
                "channel_id": str(channel.id),
                "text": "Test chunk text",
                "speaker": "Host",
                "speakers": ["Host"],
                "start_ms": 0,
                "end_ms": 5000,
                "score": 0.95,
            },
        ]

        # Preload entities
        await service.preload_entities(vector_results)

        # Verify entities were cached
        assert episode.id in service._episode_cache
        assert channel.id in service._channel_cache

        # Enrich results
        results = await service.enrich_results(vector_results)

        assert len(results) == 1
        assert results[0].episode_title == "Enrichment Test Episode"
        assert results[0].channel_name == "Enrichment Test Channel"
