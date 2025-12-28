"""Embedding tasks for Celery."""
import hashlib
import json
from typing import Optional
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.services.cache import CacheService, EmbeddingCache
from app.services.embedding import EmbeddingService
from app.tasks.async_helpers import run_async  # Efficient async runner

logger = get_task_logger(__name__)


def get_embedding_cache_key(text: str) -> str:
    """Generate cache key for embedding."""
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
    return f"emb:{text_hash}"


@celery_app.task(
    bind=True,
    name="app.tasks.embedding.embed_chunks",
    max_retries=3,
    default_retry_delay=30,
)
def embed_chunks_task(self, chunks: list[dict]) -> list[list[float]]:
    """
    Generate embeddings for a list of chunks.

    Uses batched caching to avoid re-embedding identical text.
    """
    logger.info(f"Embedding {len(chunks)} chunks")

    async def _embed():
        embedding_cache = EmbeddingCache()
        embedding_service = EmbeddingService()

        texts = [c["text"] for c in chunks]

        # Batch check cache for all texts at once
        cached_embeddings = await embedding_cache.get_many(texts)

        # Separate hits from misses
        embeddings = []
        texts_to_embed = []
        text_indices = []

        for i, text in enumerate(texts):
            if text in cached_embeddings:
                embeddings.append((i, cached_embeddings[text]))
            else:
                texts_to_embed.append(text)
                text_indices.append(i)

        logger.info(f"Cache hits: {len(embeddings)}, misses: {len(texts_to_embed)}")

        # Generate embeddings for cache misses using parallel method
        if texts_to_embed:
            new_embeddings = await embedding_service.embed_texts_parallel(texts_to_embed, max_concurrent=5)

            # Batch cache new embeddings
            new_cache_entries = {text: emb for text, emb in zip(texts_to_embed, new_embeddings)}
            await embedding_cache.set_many(new_cache_entries)

            # Collect results
            for idx, emb in zip(text_indices, new_embeddings):
                embeddings.append((idx, emb))

        # Sort by original index and return
        embeddings.sort(key=lambda x: x[0])
        return [e[1] for e in embeddings]

    return run_async(_embed())


@celery_app.task(
    bind=True,
    name="app.tasks.embedding.embed_query",
    max_retries=3,
    default_retry_delay=10,
)
def embed_query_task(self, query: str) -> list[float]:
    """
    Generate embedding for a search query.

    Uses caching with shorter TTL for queries.
    """
    logger.debug(f"Embedding query: {query[:50]}...")

    async def _embed():
        cache = CacheService()
        embedding_service = EmbeddingService()

        cache_key = get_embedding_cache_key(query)
        cached = await cache.get(cache_key)

        if cached:
            logger.debug("Query embedding cache hit")
            return json.loads(cached)

        embedding = await embedding_service.embed_query(query)

        # Cache query embeddings for 1 hour
        await cache.set(cache_key, json.dumps(embedding), ttl=3600)

        return embedding

    return run_async(_embed())


@celery_app.task(
    bind=True,
    name="app.tasks.embedding.batch_embed",
)
def batch_embed_task(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """
    Embed a large number of texts in batches.

    For bulk operations like re-indexing.
    """
    logger.info(f"Batch embedding {len(texts)} texts")

    async def _batch_embed():
        embedding_service = EmbeddingService()
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await embedding_service.embed_texts(batch)
            all_embeddings.extend(embeddings)
            logger.info(f"Embedded batch {i // batch_size + 1}")

        return all_embeddings

    return run_async(_batch_embed())


@celery_app.task(
    bind=True,
    name="app.tasks.embedding.warm_cache",
)
def warm_embedding_cache(self, queries: list[str]):
    """
    Pre-warm the embedding cache with common queries.

    Called periodically to keep popular queries fast.
    """
    logger.info(f"Warming cache with {len(queries)} queries")

    async def _warm():
        cache = CacheService()
        embedding_service = EmbeddingService()

        warmed = 0
        for query in queries:
            cache_key = get_embedding_cache_key(query)
            if not await cache.exists(cache_key):
                embedding = await embedding_service.embed_query(query)
                await cache.set(cache_key, json.dumps(embedding), ttl=3600)
                warmed += 1

        logger.info(f"Warmed {warmed} embeddings")
        return {"warmed": warmed, "total": len(queries)}

    return run_async(_warm())
