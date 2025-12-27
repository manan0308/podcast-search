import time
import uuid
from datetime import datetime
from uuid import UUID
from loguru import logger
import anthropic

from app.config import settings
from app.services.search import SearchService
from app.schemas.search import SearchResult
from app.schemas.chat import ChatResponse, Citation
from app.utils.retry import retry_async, anthropic_circuit


class RAGService:
    """RAG-powered chat using Claude with podcast transcripts as context."""

    def __init__(self, search_service: SearchService):
        self.search_service = search_service
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    async def chat(
        self,
        message: str,
        conversation_id: UUID | None = None,
        conversation_history: list[dict] | None = None,
        speaker: str | None = None,
        channel_id: UUID | None = None,
        channel_slug: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        max_context_chunks: int = 10,
    ) -> ChatResponse:
        """
        Answer questions using RAG.

        Args:
            message: User's question
            conversation_id: Optional conversation ID for multi-turn
            conversation_history: Previous messages in conversation
            speaker: Filter sources by speaker
            channel_id: Filter sources by channel
            channel_slug: Filter sources by channel slug
            date_from: Filter sources by date range
            date_to: Filter sources by date range
            max_context_chunks: Maximum chunks to include in context

        Returns:
            ChatResponse with answer and citations
        """
        start_time = time.time()

        logger.info(f"RAG query: {message}")

        # Generate or use existing conversation ID
        conv_id = conversation_id or uuid.uuid4()

        # Search for relevant chunks
        search_results, _ = await self.search_service.search(
            query=message,
            limit=max_context_chunks,
            speaker=speaker,
            channel_id=channel_id,
            channel_slug=channel_slug,
            date_from=date_from,
            date_to=date_to,
            include_context=False,  # We'll use chunks directly
        )

        if not search_results:
            # No relevant content found
            return ChatResponse(
                answer="I couldn't find any relevant information in the podcast transcripts to answer your question. Try rephrasing your question or broadening your search filters.",
                citations=[],
                conversation_id=conv_id,
                search_results_used=0,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        # Build context from search results
        context = self._build_context(search_results)

        # Build messages
        messages = self._build_messages(
            message=message,
            context=context,
            conversation_history=conversation_history or [],
        )

        # Call Claude with retry and circuit breaker
        try:
            answer = await self._call_claude_with_retry(messages)

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return ChatResponse(
                answer="I encountered an error while generating a response. Please try again.",
                citations=[],
                conversation_id=conv_id,
                search_results_used=len(search_results),
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        # Build citations
        citations = self._build_citations(search_results)

        processing_time = int((time.time() - start_time) * 1000)
        logger.info(f"RAG response generated in {processing_time}ms")

        return ChatResponse(
            answer=answer,
            citations=citations,
            conversation_id=conv_id,
            search_results_used=len(search_results),
            processing_time_ms=processing_time,
        )

    @retry_async(
        max_retries=3,
        initial_delay=1.0,
        exceptions=(anthropic.APIError, anthropic.APITimeoutError),
    )
    @anthropic_circuit
    async def _call_claude_with_retry(self, messages: list[dict]) -> str:
        """Call Claude API with retry and circuit breaker."""
        import asyncio

        # Run sync client in thread pool
        def _call():
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=messages,
            )
            return response.content[0].text

        return await asyncio.get_event_loop().run_in_executor(None, _call)

    def _get_system_prompt(self) -> str:
        """System prompt for RAG with strict grounding."""
        return """You are an assistant that answers questions about podcasts based on their transcripts.

You have access to transcript excerpts that will be provided as context. Use this context to answer questions accurately.

## STRICT GROUNDING RULES (CRITICAL):
1. Base your answers ONLY on the provided transcript excerpts - never make up information
2. For EVERY claim you make, include a short quoted span (5-15 words) from the transcript
3. Format quotes as: "quoted text" [Source N]
4. If the context doesn't contain enough information, say "I couldn't find information about this in the transcripts" and suggest a better query
5. Never hallucinate or infer beyond what's explicitly stated

## CITATION FORMAT:
- Use inline citations: "quoted text" [1]
- At the end, list sources: [1] Speaker Name, Episode Title, Timestamp
- Quote the most relevant 5-15 word spans that support your answer

## QUALITY GUIDELINES:
- Distinguish between what different speakers said
- If asked about opinions, attribute them: "According to [Speaker], ..."
- If multiple sources support a point, cite all of them
- Be concise but thorough
- If confidence is low, acknowledge uncertainty

## EXAMPLE RESPONSE:
The speaker discusses how "compound interest is the eighth wonder of the world" [1] and emphasizes that "starting early is more important than starting big" [2].

Sources:
[1] Ray Dalio, WTF Is Wealth?, 12:34
[2] Nikhil Kamath, WTF Is Wealth?, 15:22"""

    def _build_context(self, search_results: list[SearchResult]) -> str:
        """Build context string from search results."""
        context_parts = []

        for i, result in enumerate(search_results, 1):
            context_parts.append(f"""
[Source {i}]
Episode: {result.episode_title}
Speaker: {result.speaker or "Unknown"}
Channel: {result.channel_name}
Timestamp: {result.timestamp}
---
{result.text}
---
""")

        return "\n".join(context_parts)

    def _build_messages(
        self,
        message: str,
        context: str,
        conversation_history: list[dict],
    ) -> list[dict]:
        """Build message list for Claude API."""
        messages = []

        # Add conversation history
        for msg in conversation_history[-10:]:  # Keep last 10 messages
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # Add current message with context
        user_message = f"""Based on the following podcast transcript excerpts, please answer my question.

CONTEXT:
{context}

QUESTION:
{message}

Remember to cite the specific episode and speaker when referencing information from the transcripts."""

        messages.append({
            "role": "user",
            "content": user_message,
        })

        return messages

    def _build_citations(self, search_results: list[SearchResult]) -> list[Citation]:
        """Build citation list from search results."""
        citations = []

        for result in search_results:
            citations.append(Citation(
                episode_id=result.episode_id,
                episode_title=result.episode_title,
                episode_url=result.episode_url,
                channel_name=result.channel_name,
                channel_slug=result.channel_slug,
                speaker=result.speaker,
                text=result.text[:500] + "..." if len(result.text) > 500 else result.text,
                timestamp=result.timestamp,
                timestamp_ms=result.timestamp_ms,
                published_at=result.published_at,
            ))

        return citations
