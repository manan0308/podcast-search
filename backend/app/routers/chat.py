from fastapi import APIRouter

from app.dependencies import DB
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.search import SearchService
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.rag import RAGService

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: DB,
):
    """
    RAG-powered chat about podcast content.

    Ask questions about any transcribed podcast content and get
    answers with citations to specific episodes and timestamps.

    Filters:
    - speaker: Only use content from a specific speaker
    - channel_id: Only use content from a specific channel
    - channel_slug: Only use content from a specific channel (by slug)
    - date_from: Only use content from after this date
    - date_to: Only use content from before this date
    """
    embedding_service = EmbeddingService()
    vector_store = VectorStoreService()
    search_service = SearchService(
        db=db,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )
    rag_service = RAGService(search_service=search_service)

    filters = request.filters or {}

    response = await rag_service.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        speaker=filters.speaker if hasattr(filters, "speaker") else None,
        channel_id=filters.channel_id if hasattr(filters, "channel_id") else None,
        channel_slug=filters.channel_slug if hasattr(filters, "channel_slug") else None,
        date_from=filters.date_from if hasattr(filters, "date_from") else None,
        date_to=filters.date_to if hasattr(filters, "date_to") else None,
        max_context_chunks=request.max_context_chunks,
    )

    return response


@router.post("/simple")
async def simple_chat(
    message: str,
    db: DB,
    channel_slug: str | None = None,
    speaker: str | None = None,
):
    """
    Simple chat endpoint for quick queries.

    This is a convenience endpoint that accepts query parameters
    instead of a JSON body.
    """
    embedding_service = EmbeddingService()
    vector_store = VectorStoreService()
    search_service = SearchService(
        db=db,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )
    rag_service = RAGService(search_service=search_service)

    response = await rag_service.chat(
        message=message,
        channel_slug=channel_slug,
        speaker=speaker,
    )

    return {
        "answer": response.answer,
        "citations": len(response.citations),
    }
