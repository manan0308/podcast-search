import secrets
import time
from collections import OrderedDict
from threading import Lock
from typing import Annotated
from fastapi import Depends, Header, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import QdrantClient
from loguru import logger

from app.database import get_db
from app.config import settings


# LRU cache with size limit for rate limiting (prevents memory exhaustion)
class LRURateLimitCache:
    """Thread-safe LRU cache for rate limiting with bounded size."""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.cache: OrderedDict[str, list[float]] = OrderedDict()
        self.lock = Lock()

    def get(self, key: str) -> list[float]:
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
            return []

    def set(self, key: str, timestamps: list[float]):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                # Evict oldest entries if at capacity
                while len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)
            self.cache[key] = timestamps

    def cleanup_old_entries(self, max_age_seconds: int = 300):
        """Remove entries older than max_age_seconds (call periodically)."""
        now = time.time()
        cutoff = now - max_age_seconds
        with self.lock:
            keys_to_remove = []
            for key, timestamps in self.cache.items():
                # Remove if all timestamps are old
                if not timestamps or max(timestamps) < cutoff:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del self.cache[key]


# In-memory fallback for rate limiting with bounded size
_rate_limit_cache = LRURateLimitCache(max_size=10000)

# Redis client singleton for rate limiting
_redis_client = None


async def _get_rate_limit_redis():
    """Get Redis client for rate limiting."""
    global _redis_client
    if _redis_client is None and settings.REDIS_URL:
        try:
            import redis.asyncio as redis

            _redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for rate limiting: {e}")
            return None
    return _redis_client


async def get_qdrant() -> QdrantClient:
    """Dependency for getting Qdrant client with timeout."""
    client = QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY,
        timeout=30,  # Add timeout to prevent hanging
    )
    return client


async def verify_admin_secret(
    x_admin_secret: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> bool:
    """
    Dependency for verifying admin access.

    Accepts either:
    - X-Admin-Secret header
    - Authorization: Bearer <token> header
    """
    # Extract token from Authorization header if present
    token = x_admin_secret
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, settings.ADMIN_SECRET):
        logger.warning("Invalid admin authentication attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


async def rate_limit(
    request: Request,
    limit: int = 100,
    window_seconds: int = 60,
) -> None:
    """
    Rate limiting dependency with Redis support.

    Uses Redis for distributed rate limiting across multiple workers.
    Falls back to in-memory cache if Redis unavailable.

    Args:
        limit: Max requests per window
        window_seconds: Time window in seconds
    """
    # Get client identifier (IP or API key)
    client_id = request.client.host if request.client else "unknown"
    rate_key = f"rate:{client_id}"

    # Try Redis first for distributed rate limiting
    redis_client = await _get_rate_limit_redis()
    if redis_client:
        try:
            # Use Redis sliding window with sorted set
            now = time.time()
            window_start = now - window_seconds

            # Start pipeline
            pipe = redis_client.pipeline()
            # Remove old entries
            pipe.zremrangebyscore(rate_key, 0, window_start)
            # Count current entries
            pipe.zcard(rate_key)
            # Add current request
            pipe.zadd(rate_key, {str(now): now})
            # Set expiry
            pipe.expire(rate_key, window_seconds + 1)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {limit} requests per {window_seconds}s",
                    headers={"Retry-After": str(window_seconds)},
                )
            return

        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limit error, falling back to memory: {e}")

    # Fallback to in-memory rate limiting with LRU cache
    now = time.time()
    window_start = now - window_seconds

    # Get request timestamps for this client
    timestamps = _rate_limit_cache.get(client_id)

    # Filter to current window
    timestamps = [ts for ts in timestamps if ts > window_start]

    # Check limit
    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {limit} requests per {window_seconds}s",
            headers={"Retry-After": str(window_seconds)},
        )

    # Record this request
    timestamps.append(now)
    _rate_limit_cache.set(client_id, timestamps)


async def verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency for API key authentication.

    Accepts either:
    - Authorization: Bearer <api_key> header
    - X-API-Key: <api_key> header

    Returns:
        APIKey model if valid

    Raises:
        HTTPException if invalid or missing
    """
    from app.services.api_key import APIKeyService

    # Extract key from headers
    key = x_api_key
    if not key and authorization:
        if authorization.startswith("Bearer "):
            key = authorization[7:]

    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate key
    service = APIKeyService(db)
    api_key = await service.validate_key(key)

    if not api_key:
        logger.warning(f"Invalid API key attempt: {key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key


# Type aliases for cleaner dependency injection
DB = Annotated[AsyncSession, Depends(get_db)]
Qdrant = Annotated[QdrantClient, Depends(get_qdrant)]
AdminAuth = Annotated[bool, Depends(verify_admin_secret)]
APIKeyAuth = Annotated["APIKey", Depends(verify_api_key)]
