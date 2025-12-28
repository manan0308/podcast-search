"""Unit tests for cache service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.cache import CacheService, EmbeddingCache, SearchCache


class TestCacheService:
    """Tests for base cache service."""

    @pytest.mark.asyncio
    async def test_get_returns_none_on_error(self):
        """Cache get should return None on Redis error."""
        service = CacheService()

        with patch.object(service, "_get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value.get = AsyncMock(
                side_effect=Exception("Redis error")
            )

            result = await service.get("test_key")

            assert result is None

    @pytest.mark.asyncio
    async def test_set_returns_false_on_error(self):
        """Cache set should return False on Redis error."""
        service = CacheService()

        with patch.object(service, "_get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value.setex = AsyncMock(
                side_effect=Exception("Redis error")
            )

            result = await service.set("key", "value", ttl=60)

            assert result is False

    @pytest.mark.asyncio
    async def test_get_json_parses_correctly(self):
        """get_json should parse JSON correctly."""
        service = CacheService()

        with patch.object(service, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = '{"key": "value", "num": 42}'

            result = await service.get_json("test_key")

            assert result == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_get_json_returns_none_on_invalid_json(self):
        """get_json should return None for invalid JSON."""
        service = CacheService()

        with patch.object(service, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "not valid json{"

            result = await service.get_json("test_key")

            assert result is None


class TestEmbeddingCache:
    """Tests for embedding cache."""

    def test_key_generation_is_deterministic(self):
        """Same text should generate same key."""
        cache = EmbeddingCache.__new__(EmbeddingCache)
        cache.prefix = "emb"

        key1 = cache._key("hello world")
        key2 = cache._key("hello world")

        assert key1 == key2

    def test_different_text_different_key(self):
        """Different text should generate different keys."""
        cache = EmbeddingCache.__new__(EmbeddingCache)
        cache.prefix = "emb"

        key1 = cache._key("hello world")
        key2 = cache._key("goodbye world")

        assert key1 != key2


class TestSearchCache:
    """Tests for search cache."""

    def test_key_includes_filters(self):
        """Cache key should include filters."""
        cache = SearchCache.__new__(SearchCache)
        cache.prefix = "search"

        key1 = cache._key("query", {"speaker": "Host"}, 10)
        key2 = cache._key("query", {"speaker": "Guest"}, 10)

        assert key1 != key2

    def test_key_includes_limit(self):
        """Cache key should include limit."""
        cache = SearchCache.__new__(SearchCache)
        cache.prefix = "search"

        key1 = cache._key("query", None, 10)
        key2 = cache._key("query", None, 20)

        assert key1 != key2
