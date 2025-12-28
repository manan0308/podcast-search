import uuid
from datetime import datetime
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
    SearchParams,
    PayloadSchemaType,
)

from app.config import settings


class VectorStoreService:
    """Service for managing vector embeddings in Qdrant."""

    def __init__(self, client: QdrantClient | None = None):
        self.client = client or QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.vector_size = settings.EMBEDDING_DIMENSIONS

    async def ensure_collection(self) -> None:
        """Ensure the collection exists with proper schema."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )

            # Create payload indexes for filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="channel_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="episode_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="speaker",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            # published_at is stored as string, can be filtered as text
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="published_at",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            logger.info(f"Collection {self.collection_name} created")
        else:
            logger.debug(f"Collection {self.collection_name} already exists")

    async def upsert_chunks(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> list[str]:
        """
        Insert or update chunk vectors.

        Args:
            chunks: List of chunk dicts with metadata
            embeddings: Corresponding embedding vectors

        Returns:
            List of point IDs (UUIDs as strings)
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")

        if not chunks:
            return []

        await self.ensure_collection()

        points = []
        point_ids = []

        for chunk, embedding in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)

            # Prepare payload
            payload = {
                "chunk_id": str(chunk.get("chunk_id", point_id)),
                "episode_id": str(chunk["episode_id"]),
                "channel_id": str(chunk["channel_id"]),
                "speaker": chunk.get("primary_speaker"),
                "speakers": chunk.get("speakers", []),
                "text": chunk["text"],
                "episode_title": chunk.get("episode_title", ""),
                "channel_name": chunk.get("channel_name", ""),
                "channel_slug": chunk.get("channel_slug", ""),
                "start_ms": chunk.get("start_ms", 0),
                "end_ms": chunk.get("end_ms", 0),
                "chunk_index": chunk.get("chunk_index", 0),
                "word_count": chunk.get("word_count", 0),
            }

            # Add published_at if available
            if chunk.get("published_at"):
                pub_at = chunk["published_at"]
                if isinstance(pub_at, datetime):
                    payload["published_at"] = pub_at.isoformat()
                else:
                    payload["published_at"] = str(pub_at)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            )

        # Upsert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
            logger.debug(f"Upserted batch {i // batch_size + 1}")

        logger.info(f"Upserted {len(points)} vectors to Qdrant")
        return point_ids

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        speaker: str | None = None,
        channel_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        score_threshold: float = 0.3,
    ) -> list[dict]:
        """
        Search for similar chunks.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            speaker: Filter by speaker name
            channel_id: Filter by channel ID
            date_from: Filter by minimum published date
            date_to: Filter by maximum published date
            score_threshold: Minimum similarity score

        Returns:
            List of result dicts with payload and score
        """
        # Build filter conditions
        conditions = []

        if speaker:
            conditions.append(
                FieldCondition(
                    key="speaker",
                    match=MatchValue(value=speaker),
                )
            )

        if channel_id:
            conditions.append(
                FieldCondition(
                    key="channel_id",
                    match=MatchValue(value=str(channel_id)),
                )
            )

        if date_from or date_to:
            range_filter = {}
            if date_from:
                range_filter["gte"] = date_from.isoformat()
            if date_to:
                range_filter["lte"] = date_to.isoformat()

            conditions.append(
                FieldCondition(
                    key="published_at",
                    range=Range(**range_filter),
                )
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=score_threshold,
            search_params=SearchParams(
                hnsw_ef=128,
                exact=False,
            ),
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                **r.payload,
            }
            for r in results
        ]

    async def delete_by_episode(self, episode_id: str) -> int:
        """
        Delete all vectors for an episode.

        Args:
            episode_id: Episode ID

        Returns:
            Number of deleted points
        """
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="episode_id",
                        match=MatchValue(value=str(episode_id)),
                    )
                ]
            ),
        )

        logger.info(f"Deleted vectors for episode {episode_id}")
        return result.status

    async def delete_by_channel(self, channel_id: str) -> int:
        """
        Delete all vectors for a channel.

        Args:
            channel_id: Channel ID

        Returns:
            Number of deleted points
        """
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="channel_id",
                        match=MatchValue(value=str(channel_id)),
                    )
                ]
            ),
        )

        logger.info(f"Deleted vectors for channel {channel_id}")
        return result.status

    async def get_collection_stats(self) -> dict:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
