from fastapi import APIRouter, Depends, Request
from loguru import logger

from app.dependencies import DB, rate_limit
from app.schemas.search import SearchRequest, SearchResponse
from app.config import settings
from app.services.search import SearchService
from app.services.hybrid_search import HybridSearchService
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.reranker import RerankerService

router = APIRouter()


async def search_rate_limit(request: Request):
    """Rate limit for search endpoint."""
    await rate_limit(
        request,
        limit=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW,
    )


@router.post(
    "", response_model=SearchResponse, dependencies=[Depends(search_rate_limit)]
)
async def search(
    request: SearchRequest,
    db: DB,
):
    """
    Search across all podcast transcripts.

    Supports both:
    - Semantic-only search (fast, good for conceptual queries)
    - Hybrid search (semantic + BM25 keyword) with cross-encoder re-ranking (more accurate)

    Filters:
    - speaker: Filter by speaker name (e.g., "Sam Parr")
    - channel_id: Filter by channel UUID
    - channel_slug: Filter by channel slug (alternative to channel_id)
    - date_from: Filter by minimum published date
    - date_to: Filter by maximum published date

    Options:
    - use_hybrid: Enable hybrid search (default: true)
    - use_reranking: Enable cross-encoder re-ranking (default: true)
    - semantic_weight: Weight for semantic search 0-1 (default: 0.7)
    - keyword_weight: Weight for BM25 keyword search 0-1 (default: 0.3)
    """
    filters = request.filters

    # Use hybrid search if enabled (default)
    if request.use_hybrid:
        logger.info(
            f"Hybrid search: '{request.query}' (semantic={request.semantic_weight}, keyword={request.keyword_weight}, rerank={request.use_reranking})"
        )

        embedding_service = EmbeddingService()
        vector_store = VectorStoreService()
        reranker = RerankerService()

        hybrid_service = HybridSearchService(
            db=db,
            embedding_service=embedding_service,
            vector_store=vector_store,
            reranker=reranker,
            use_cache=True,
        )

        results, processing_time = await hybrid_service.search(
            query=request.query,
            limit=request.limit,
            speaker=filters.speaker if filters else None,
            channel_id=filters.channel_id if filters else None,
            channel_slug=filters.channel_slug if filters else None,
            date_from=filters.date_from if filters else None,
            date_to=filters.date_to if filters else None,
            include_context=request.include_context,
            context_utterances=request.context_utterances,
            use_reranking=request.use_reranking,
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
        )
    else:
        # Fall back to semantic-only search
        logger.info(f"Semantic search: '{request.query}'")

        embedding_service = EmbeddingService()
        vector_store = VectorStoreService()
        search_service = SearchService(
            db=db,
            embedding_service=embedding_service,
            vector_store=vector_store,
        )

        results, processing_time = await search_service.search(
            query=request.query,
            limit=request.limit,
            speaker=filters.speaker if filters else None,
            channel_id=filters.channel_id if filters else None,
            channel_slug=filters.channel_slug if filters else None,
            date_from=filters.date_from if filters else None,
            date_to=filters.date_to if filters else None,
            include_context=request.include_context,
        )

    return SearchResponse(
        results=results,
        total=len(results),
        query=request.query,
        processing_time_ms=processing_time,
    )


@router.get("/speakers")
async def get_speakers(db: DB):
    """Get all unique speakers across all channels."""
    from sqlalchemy import select, distinct
    from app.models import Channel

    result = await db.execute(select(Channel.speakers))
    all_speakers = set()

    for speakers_list in result.scalars():
        if speakers_list:
            all_speakers.update(speakers_list)

    # Also get speakers from utterances
    from app.models import Utterance

    utt_result = await db.execute(select(distinct(Utterance.speaker)))
    for speaker in utt_result.scalars():
        if speaker:
            all_speakers.add(speaker)

    return {"speakers": sorted(list(all_speakers))}


@router.get("/stats")
async def get_search_stats(db: DB):
    """Get search statistics."""
    from sqlalchemy import select, func
    from app.models import Channel, Episode, Chunk

    # Count channels
    channels_result = await db.execute(select(func.count(Channel.id)))
    channel_count = channels_result.scalar()

    # Count episodes
    episodes_result = await db.execute(select(func.count(Episode.id)))
    episode_count = episodes_result.scalar()

    # Count transcribed episodes
    transcribed_result = await db.execute(
        select(func.count(Episode.id)).where(Episode.status == "done")
    )
    transcribed_count = transcribed_result.scalar()

    # Count chunks
    chunks_result = await db.execute(select(func.count(Chunk.id)))
    chunk_count = chunks_result.scalar()

    # Get vector store stats
    vector_store = VectorStoreService()
    vector_stats = await vector_store.get_collection_stats()

    return {
        "channels": channel_count,
        "episodes": episode_count,
        "transcribed_episodes": transcribed_count,
        "chunks": chunk_count,
        "vectors": vector_stats.get("points_count", 0),
    }
