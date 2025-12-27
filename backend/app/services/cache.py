"""Redis caching service with retry logic."""
import json
import hashlib
import asyncio
from typing import Any, Optional
from loguru import logger
import redis.asyncio as redis

from app.config import settings


# Simple retry decorator for Redis operations
async def _retry_redis(func, max_retries: int = 2, delay: float = 0.5):
    """Retry Redis operations with exponential backoff."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except (redis.ConnectionError, redis.TimeoutError) as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(delay * (2 ** attempt))
                logger.warning(f"Redis retry {attempt + 1}/{max_retries}: {e}")
    raise last_error


class CacheService:
    """Redis-based caching for embeddings and search results."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            if not settings.REDIS_URL:
                raise ValueError("REDIS_URL not configured")

            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        try:
            r = await self._get_redis()
            return await r.get(key)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set(
        self,
        key: str,
        value: str,
        ttl: int = 3600,
    ) -> bool:
        """Set value in cache with TTL."""
        try:
            r = await self._get_redis()
            await r.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            r = await self._get_redis()
            await r.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            r = await self._get_redis()
            return await r.exists(key) > 0
        except Exception as e:
            logger.warning(f"Cache exists error: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        try:
            r = await self._get_redis()
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await r.scan(cursor, match=pattern, count=100)
                if keys:
                    await r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break

            return deleted
        except Exception as e:
            logger.warning(f"Cache clear pattern error: {e}")
            return 0

    async def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON value."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
    ) -> bool:
        """Serialize and set JSON value."""
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError):
            return False

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class EmbeddingCache:
    """Specialized cache for embeddings."""

    def __init__(self, cache: CacheService = None):
        self.cache = cache or CacheService()
        self.prefix = "emb"
        self.ttl = 86400 * 7  # 7 days

    def _key(self, text: str) -> str:
        """Generate cache key for text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
        return f"{self.prefix}:{text_hash}"

    async def get(self, text: str) -> Optional[list[float]]:
        """Get cached embedding."""
        return await self.cache.get_json(self._key(text))

    async def set(self, text: str, embedding: list[float]) -> bool:
        """Cache embedding."""
        return await self.cache.set_json(self._key(text), embedding, self.ttl)

    async def get_many(self, texts: list[str]) -> dict[str, list[float]]:
        """Get multiple cached embeddings."""
        results = {}
        for text in texts:
            emb = await self.get(text)
            if emb:
                results[text] = emb
        return results

    async def set_many(self, embeddings: dict[str, list[float]]) -> int:
        """Cache multiple embeddings."""
        cached = 0
        for text, emb in embeddings.items():
            if await self.set(text, emb):
                cached += 1
        return cached


class SearchCache:
    """Specialized cache for search results."""

    def __init__(self, cache: CacheService = None):
        self.cache = cache or CacheService()
        self.prefix = "search"
        self.ttl = 300  # 5 minutes

    def _key(
        self,
        query: str,
        filters: dict = None,
        limit: int = 10,
    ) -> str:
        """Generate cache key for search query."""
        parts = [query, str(limit)]
        if filters:
            parts.append(json.dumps(filters, sort_keys=True))
        key_str = ":".join(parts)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:32]
        return f"{self.prefix}:{key_hash}"

    async def get(
        self,
        query: str,
        filters: dict = None,
        limit: int = 10,
    ) -> Optional[list[dict]]:
        """Get cached search results."""
        key = self._key(query, filters, limit)
        return await self.cache.get_json(key)

    async def set(
        self,
        query: str,
        results: list[dict],
        filters: dict = None,
        limit: int = 10,
    ) -> bool:
        """Cache search results."""
        key = self._key(query, filters, limit)
        return await self.cache.set_json(key, results, self.ttl)

    async def invalidate(self) -> int:
        """Invalidate all search cache."""
        return await self.cache.clear_pattern(f"{self.prefix}:*")
