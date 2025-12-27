import asyncio
from typing import List
from loguru import logger
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class EmbeddingService:
    """Generate embeddings using OpenAI."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_texts(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []

        logger.info(f"Generating embeddings for {len(texts)} texts")

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = await self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
            )

            # Extract embeddings in order
            batch_embeddings = [None] * len(batch)
            for item in response.data:
                batch_embeddings[item.index] = item.embedding

            all_embeddings.extend(batch_embeddings)

            logger.debug(f"Embedded batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}")

        logger.info(f"Generated {len(all_embeddings)} embeddings")
        return all_embeddings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a single search query.

        Args:
            query: Search query text

        Returns:
            Embedding vector
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=query,
            dimensions=self.dimensions,
        )

        return response.data[0].embedding

    async def embed_texts_parallel(
        self,
        texts: list[str],
        batch_size: int = 100,
        max_concurrent: int = 5,
    ) -> list[list[float]]:
        """
        Generate embeddings with parallel batch processing.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
            max_concurrent: Maximum concurrent API calls

        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []

        logger.info(f"Generating embeddings for {len(texts)} texts (parallel)")

        # Split into batches
        batches = [
            texts[i:i + batch_size]
            for i in range(0, len(texts), batch_size)
        ]

        # Semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_batch(batch: list[str], batch_idx: int):
            async with semaphore:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                )

                # Extract embeddings in order
                batch_embeddings = [None] * len(batch)
                for item in response.data:
                    batch_embeddings[item.index] = item.embedding

                return batch_idx, batch_embeddings

        # Process all batches concurrently
        tasks = [
            embed_batch(batch, idx)
            for idx, batch in enumerate(batches)
        ]

        results = await asyncio.gather(*tasks)

        # Reassemble in order
        all_embeddings = []
        for batch_idx, batch_embeddings in sorted(results, key=lambda x: x[0]):
            all_embeddings.extend(batch_embeddings)

        logger.info(f"Generated {len(all_embeddings)} embeddings")
        return all_embeddings
