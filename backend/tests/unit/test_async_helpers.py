"""Tests for async helpers used in Celery tasks."""

import asyncio
import pytest

from app.tasks.async_helpers import run_async, get_event_loop, cleanup_loop


class TestAsyncHelpers:
    """Test suite for async helper functions."""

    def test_get_event_loop_creates_new_loop(self):
        """Test that get_event_loop creates a new loop if none exists."""
        # Clean up any existing loop first
        cleanup_loop()

        loop = get_event_loop()
        assert loop is not None
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert not loop.is_closed()

        # Cleanup
        cleanup_loop()

    def test_get_event_loop_reuses_existing_loop(self):
        """Test that get_event_loop returns the same loop on subsequent calls."""
        cleanup_loop()

        loop1 = get_event_loop()
        loop2 = get_event_loop()

        assert loop1 is loop2

        cleanup_loop()

    def test_run_async_executes_coroutine(self):
        """Test that run_async properly executes a coroutine."""

        async def sample_coro():
            await asyncio.sleep(0)
            return "success"

        result = run_async(sample_coro())
        assert result == "success"

        cleanup_loop()

    def test_run_async_handles_exceptions(self):
        """Test that run_async properly propagates exceptions."""

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing_coro())

        cleanup_loop()

    def test_run_async_with_db_operations(self):
        """Test run_async with database-like async operations."""

        async def mock_db_operation():
            await asyncio.sleep(0.01)
            return {"id": 1, "name": "test"}

        result = run_async(mock_db_operation())
        assert result == {"id": 1, "name": "test"}

        cleanup_loop()

    def test_cleanup_loop_closes_loop(self):
        """Test that cleanup_loop properly closes the event loop."""
        loop = get_event_loop()
        assert not loop.is_closed()

        cleanup_loop()

        # After cleanup, get_event_loop should create a new loop
        new_loop = get_event_loop()
        assert new_loop is not loop

        cleanup_loop()

    def test_multiple_run_async_calls_same_loop(self):
        """Test that multiple run_async calls use the same event loop."""
        cleanup_loop()

        results = []

        async def append_result(value):
            await asyncio.sleep(0)
            results.append(value)
            return value

        run_async(append_result(1))
        run_async(append_result(2))
        run_async(append_result(3))

        assert results == [1, 2, 3]

        cleanup_loop()


class TestProviderFactory:
    """Test suite for transcription provider factory."""

    def test_get_available_providers_returns_list(self):
        """Test that get_available_providers returns a list of providers."""
        from app.services.transcription.factory import get_available_providers

        providers = get_available_providers()

        assert isinstance(providers, list)
        assert len(providers) > 0

        # Check that each provider has required fields
        for provider in providers:
            assert "name" in provider
            assert "display_name" in provider
            assert "available" in provider
            assert "max_concurrent" in provider
            assert "cost_per_hour_cents" in provider

    def test_faster_whisper_is_available(self):
        """Test that faster-whisper is available in the container."""
        from app.services.transcription.factory import get_available_providers

        providers = get_available_providers()
        faster_whisper = next(
            (p for p in providers if p["name"] == "faster-whisper"), None
        )

        assert faster_whisper is not None
        assert faster_whisper["available"] is True
        assert faster_whisper["cost_per_hour_cents"] == 0

    def test_get_provider_returns_correct_instance(self):
        """Test that get_provider returns the correct provider instance."""
        from app.services.transcription.factory import get_provider
        from app.services.transcription.faster_whisper import FasterWhisperProvider

        provider = get_provider("faster-whisper")
        assert isinstance(provider, FasterWhisperProvider)

    def test_get_provider_raises_for_unknown(self):
        """Test that get_provider raises ValueError for unknown provider."""
        from app.services.transcription.factory import get_provider

        with pytest.raises(ValueError, match="Unknown transcription provider"):
            get_provider("unknown-provider")


class TestEmbeddingCache:
    """Test suite for embedding cache batch operations."""

    @pytest.mark.asyncio
    async def test_get_many_returns_dict(self):
        """Test that get_many returns a dictionary."""
        from app.services.cache import EmbeddingCache

        cache = EmbeddingCache()

        # Test with empty list
        result = await cache.get_many([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_set_many_returns_count(self):
        """Test that set_many returns the count of cached items."""
        from app.services.cache import EmbeddingCache

        cache = EmbeddingCache()

        # Test with empty dict
        result = await cache.set_many({})
        assert result == 0
