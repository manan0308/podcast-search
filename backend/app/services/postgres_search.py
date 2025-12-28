"""
PostgreSQL Full-Text Search Service.

Replaces in-memory BM25 with database-native full-text search.
Uses PostgreSQL's ts_vector and ts_rank for efficient keyword matching.

Benefits over in-memory BM25:
- No memory overhead (doesn't load all chunks)
- Uses GIN indexes for O(log n) search
- Handles large datasets efficiently
- Supports phrase search, stemming, ranking
"""

from uuid import UUID
from typing import Optional
from dataclasses import dataclass
from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import Chunk, Episode, Channel


@dataclass
class KeywordSearchResult:
    """Result from PostgreSQL full-text search."""

    chunk_id: UUID
    episode_id: UUID
    channel_id: UUID
    text: str
    primary_speaker: str
    speakers: list[str]
    start_ms: int
    end_ms: int
    rank: float  # ts_rank score


class PostgresSearchService:
    """
    Full-text search using PostgreSQL's built-in capabilities.

    Uses:
    - to_tsvector: Converts text to searchable tokens
    - to_tsquery: Parses search query
    - ts_rank: Ranks results by relevance
    - GIN index: Fast lookups (idx_chunks_text_search)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def keyword_search(
        self,
        query: str,
        limit: int = 20,
        channel_id: Optional[UUID] = None,
        speaker: Optional[str] = None,
        min_rank: float = 0.01,
    ) -> list[KeywordSearchResult]:
        """
        Search chunks using PostgreSQL full-text search.

        Args:
            query: Search query (supports AND, OR, phrases in quotes)
            limit: Maximum results to return
            channel_id: Filter by channel
            speaker: Filter by speaker
            min_rank: Minimum relevance score

        Returns:
            List of KeywordSearchResult sorted by relevance
        """
        if not query or not query.strip():
            return []

        # Convert query to tsquery format
        # "hello world" -> 'hello' & 'world'
        # Handles phrases in quotes: "exact phrase" -> 'exact' <-> 'phrase'
        ts_query = self._build_tsquery(query)

        # Build the search query with ranking
        # Uses ts_rank_cd for better ranking of close matches
        rank_expr = func.ts_rank_cd(
            func.to_tsvector("english", Chunk.text),
            func.to_tsquery("english", ts_query),
        )

        stmt = (
            select(
                Chunk.id,
                Chunk.episode_id,
                Chunk.text,
                Chunk.primary_speaker,
                Chunk.speakers,
                Chunk.start_ms,
                Chunk.end_ms,
                rank_expr.label("rank"),
            )
            .where(
                func.to_tsvector("english", Chunk.text).op("@@")(
                    func.to_tsquery("english", ts_query)
                )
            )
            .where(rank_expr >= min_rank)
        )

        # Apply filters
        if channel_id:
            # Join with Episode to filter by channel
            stmt = stmt.join(Episode, Chunk.episode_id == Episode.id)
            stmt = stmt.where(Episode.channel_id == channel_id)

        if speaker:
            stmt = stmt.where(
                or_(
                    Chunk.primary_speaker == speaker,
                    Chunk.speakers.contains([speaker]),
                )
            )

        # Order by rank and limit
        stmt = stmt.order_by(rank_expr.desc()).limit(limit)

        result = await self.db.execute(stmt)
        rows = result.all()

        # Get channel_ids for results
        episode_ids = [row.episode_id for row in rows]
        if episode_ids:
            ep_result = await self.db.execute(
                select(Episode.id, Episode.channel_id).where(
                    Episode.id.in_(episode_ids)
                )
            )
            episode_channels = {row.id: row.channel_id for row in ep_result.all()}
        else:
            episode_channels = {}

        return [
            KeywordSearchResult(
                chunk_id=row.id,
                episode_id=row.episode_id,
                channel_id=episode_channels.get(row.episode_id),
                text=row.text,
                primary_speaker=row.primary_speaker,
                speakers=row.speakers or [],
                start_ms=row.start_ms,
                end_ms=row.end_ms,
                rank=float(row.rank),
            )
            for row in rows
        ]

    async def headline_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Search with highlighted snippets.

        Returns chunks with matching terms highlighted.
        Useful for search result previews.
        """
        if not query or not query.strip():
            return []

        ts_query = self._build_tsquery(query)

        # ts_headline highlights matching terms
        headline_expr = func.ts_headline(
            "english",
            Chunk.text,
            func.to_tsquery("english", ts_query),
            "StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=20",
        )

        rank_expr = func.ts_rank_cd(
            func.to_tsvector("english", Chunk.text),
            func.to_tsquery("english", ts_query),
        )

        stmt = (
            select(
                Chunk.id,
                Chunk.episode_id,
                headline_expr.label("headline"),
                rank_expr.label("rank"),
            )
            .where(
                func.to_tsvector("english", Chunk.text).op("@@")(
                    func.to_tsquery("english", ts_query)
                )
            )
            .order_by(rank_expr.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)

        return [
            {
                "chunk_id": str(row.id),
                "episode_id": str(row.episode_id),
                "headline": row.headline,
                "rank": float(row.rank),
            }
            for row in result.all()
        ]

    def _build_tsquery(self, query: str) -> str:
        """
        Convert user query to PostgreSQL tsquery format.

        Handles:
        - Simple words: hello world -> 'hello' & 'world'
        - Quoted phrases: "exact match" -> 'exact' <-> 'match'
        - OR operator: hello OR world -> 'hello' | 'world'

        Security:
        - Sanitizes all special characters to prevent injection
        - Limits query length
        - Validates word characters only
        """
        import re

        # Limit query length to prevent DoS
        query = query[:500]

        # Extract quoted phrases first
        phrases = re.findall(r'"([^"]+)"', query)
        remaining = re.sub(r'"[^"]+"', "", query)

        parts = []

        # Add phrase queries (adjacent words)
        for phrase in phrases:
            words = []
            for w in phrase.strip().split():
                # Only allow alphanumeric characters
                clean = re.sub(r"[^\w]", "", w)
                if clean and len(clean) <= 50:
                    # Escape single quotes
                    words.append(clean.lower().replace("'", "''"))

            if words:
                phrase_query = " <-> ".join(f"'{w}'" for w in words)
                parts.append(f"({phrase_query})")

        # Add remaining words
        remaining_words = remaining.strip().split()
        for word in remaining_words:
            word = word.strip()

            if word.upper() == "OR":
                if parts:
                    parts[-1] = parts[-1] + " |"
                continue
            elif word.upper() == "AND":
                continue  # AND is default

            # Sanitize: only alphanumeric
            clean_word = re.sub(r"[^\w]", "", word)

            if clean_word and len(clean_word) <= 50:
                # Escape single quotes
                safe_word = clean_word.lower().replace("'", "''")

                if parts and parts[-1].endswith("|"):
                    parts[-1] = parts[-1] + f" '{safe_word}'"
                else:
                    parts.append(f"'{safe_word}'")

        if not parts:
            return "''"

        result = " & ".join(p for p in parts if not p.endswith("|"))
        return result
