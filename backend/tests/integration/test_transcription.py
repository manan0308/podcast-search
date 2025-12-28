"""Integration tests for transcription pipeline."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestTranscriptionPipeline:
    """Test suite for transcription pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_uses_correct_event_loop(self):
        """Test that the pipeline doesn't create conflicting event loops."""
        from app.tasks.async_helpers import run_async, cleanup_loop, get_event_loop

        cleanup_loop()

        # Get the loop that would be used
        loop = get_event_loop()

        # Run an async operation
        async def sample_operation():
            return "success"

        result = run_async(sample_operation())
        assert result == "success"

        # Verify we're still using the same loop
        current_loop = get_event_loop()
        assert current_loop is loop

        cleanup_loop()

    @pytest.mark.asyncio
    async def test_speaker_labeling_uses_async_client(self):
        """Test that speaker labeling uses async Anthropic client."""
        from app.services.speaker_labeling import SpeakerLabelingService
        import anthropic

        service = SpeakerLabelingService()

        # Verify the client is async
        assert isinstance(service.client, anthropic.AsyncAnthropic)

    def test_maintenance_uses_efficient_async_runner(self):
        """Test that maintenance tasks use the efficient async runner."""
        # Import the module to check the import
        from app.tasks import maintenance

        # Verify it imports from async_helpers, not defines its own run_async
        import inspect
        source = inspect.getsource(maintenance)

        assert "from app.tasks.async_helpers import run_async" in source
        # Should not have its own run_async definition at module level
        assert "def run_async(" not in source


class TestProviderIntegration:
    """Test provider availability and configuration."""

    def test_all_free_providers_available(self):
        """Test that at least one free provider is available."""
        from app.services.transcription.factory import get_available_providers

        providers = get_available_providers()
        free_available = [
            p for p in providers
            if p["available"] and p["cost_per_hour_cents"] == 0
        ]

        assert len(free_available) > 0, "At least one free provider should be available"

    def test_faster_whisper_provider_initializes(self):
        """Test that FasterWhisperProvider can be initialized."""
        from app.services.transcription.factory import get_provider

        try:
            provider = get_provider("faster-whisper")
            assert provider is not None
        except ValueError as e:
            pytest.skip(f"faster-whisper not available: {e}")


class TestDatabaseConnectionPool:
    """Test database connection pool behavior."""

    @pytest.mark.asyncio
    async def test_async_session_factory_works(self):
        """Test that async_session_factory creates valid sessions."""
        from app.database import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            assert value == 1

    @pytest.mark.asyncio
    async def test_multiple_sessions_dont_conflict(self):
        """Test that multiple async sessions don't cause issues."""
        from app.database import async_session_factory
        from sqlalchemy import text

        async def query_db():
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar()

        # Run multiple concurrent queries
        results = await asyncio.gather(
            query_db(),
            query_db(),
            query_db(),
        )

        assert all(r == 1 for r in results)
