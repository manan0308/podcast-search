from dataclasses import dataclass
from uuid import UUID
from datetime import datetime
from loguru import logger

from app.config import settings


@dataclass
class Chunk:
    """A chunk of transcript text for embedding."""

    text: str  # Raw text for display
    text_for_embedding: str  # Enriched text with context headers for embedding
    primary_speaker: str | None
    speakers: list[str]
    start_ms: int
    end_ms: int
    chunk_index: int
    word_count: int


@dataclass
class EpisodeContext:
    """Context metadata for enriching chunks."""

    episode_title: str
    channel_name: str
    published_at: datetime | None = None
    episode_description: str | None = None


class ChunkingService:
    """
    Split transcripts into searchable chunks for RAG.

    Strategy:
    - Group utterances into ~500 word chunks
    - Try to break at speaker changes when possible
    - Keep track of all speakers in each chunk
    - Add overlap between chunks for context
    - Add contextual headers for better embedding quality
    """

    def __init__(
        self,
        target_chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_chunk_size: int = 100,
    ):
        self.target_chunk_size = target_chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.min_chunk_size = min_chunk_size

    def chunk_transcript(
        self,
        utterances: list[dict],
        episode_id: UUID | str,
        episode_context: EpisodeContext | None = None,
    ) -> list[Chunk]:
        """
        Split utterances into chunks for embedding.

        Args:
            utterances: List of utterance dicts with speaker, text, start_ms, end_ms
            episode_id: Episode ID for logging
            episode_context: Optional metadata for contextual chunk headers

        Returns:
            List of Chunk objects with enriched text_for_embedding
        """
        if not utterances:
            return []

        logger.info(f"Chunking transcript with {len(utterances)} utterances")

        chunks = []
        current_chunk_utterances = []
        current_word_count = 0

        for i, utt in enumerate(utterances):
            utt_word_count = len(utt.get("text", "").split())

            # Check if we should start a new chunk
            should_break = False

            if current_word_count >= self.target_chunk_size:
                should_break = True
            elif (
                current_word_count >= self.target_chunk_size * 0.7
                and self._is_good_break_point(current_chunk_utterances, utt)
            ):
                # Break at speaker change or pause if we're close to target
                should_break = True
            elif (
                current_word_count >= self.target_chunk_size * 0.5
                and self._detect_topic_shift(current_chunk_utterances, utt)
            ):
                # Break at topic shift even if smaller (min 50% of target)
                should_break = True

            if should_break and current_chunk_utterances:
                # Create chunk from accumulated utterances
                chunk = self._create_chunk(
                    current_chunk_utterances,
                    chunk_index=len(chunks),
                    episode_context=episode_context,
                )
                chunks.append(chunk)

                # Keep overlap for next chunk
                current_chunk_utterances = self._get_overlap_utterances(
                    current_chunk_utterances
                )
                current_word_count = sum(
                    len(u.get("text", "").split()) for u in current_chunk_utterances
                )

            current_chunk_utterances.append(utt)
            current_word_count += utt_word_count

        # Don't forget the last chunk
        if current_chunk_utterances:
            # Only create if it meets minimum size or it's the only chunk
            if current_word_count >= self.min_chunk_size or not chunks:
                chunk = self._create_chunk(
                    current_chunk_utterances,
                    chunk_index=len(chunks),
                    episode_context=episode_context,
                )
                chunks.append(chunk)
            elif chunks:
                # Merge with previous chunk if too small
                prev_chunk = chunks[-1]
                merged = self._create_chunk(
                    self._parse_chunk_utterances(prev_chunk) + current_chunk_utterances,
                    chunk_index=len(chunks) - 1,
                    episode_context=episode_context,
                )
                chunks[-1] = merged

        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    def _is_good_break_point(
        self, current_utterances: list[dict], next_utterance: dict
    ) -> bool:
        """
        Check if this is a good point to break the chunk.

        Uses topic-aware signals:
        1. Speaker changes (turn-taking)
        2. Long pauses (>2 seconds indicates topic shift)
        3. Sentence-ending markers (questions, statements)
        """
        if not current_utterances:
            return False

        last_utt = current_utterances[-1]
        current_speaker = last_utt.get("speaker")
        next_speaker = next_utterance.get("speaker")

        # Strong signal: speaker change
        if current_speaker != next_speaker:
            return True

        # Strong signal: long pause (>2 seconds = topic shift)
        last_end_ms = last_utt.get("end_ms", 0)
        next_start_ms = next_utterance.get("start_ms", 0)
        pause_ms = next_start_ms - last_end_ms

        if pause_ms > 2000:  # 2+ second pause
            return True

        # Moderate signal: sentence-ending + medium pause
        last_text = last_utt.get("text", "").strip()
        ends_with_terminal = last_text.endswith((".", "?", "!"))

        if ends_with_terminal and pause_ms > 1000:
            return True

        return False

    def _detect_topic_shift(
        self,
        current_utterances: list[dict],
        next_utterance: dict,
    ) -> bool:
        """
        Detect topic shifts using simple heuristics.

        Returns True if there's evidence of a topic change:
        - Explicit transition markers
        - Significant time gaps
        - Question-answer patterns
        """
        if not current_utterances:
            return False

        last_text = current_utterances[-1].get("text", "").lower()
        next_text = next_utterance.get("text", "").lower()

        # Transition markers indicating new topic
        transition_markers = [
            "anyway",
            "moving on",
            "let's talk about",
            "speaking of",
            "on another note",
            "changing topics",
            "now let's",
            "the next thing",
            "another question",
            "so tell me about",
        ]

        for marker in transition_markers:
            if marker in next_text[:100]:  # Check start of next utterance
                return True

        # Question markers (interviewer asking about new topic)
        question_starters = [
            "what about",
            "how about",
            "can you tell",
            "what do you think",
        ]
        for starter in question_starters:
            if next_text.startswith(starter):
                return True

        return False

    def _create_chunk(
        self,
        utterances: list[dict],
        chunk_index: int,
        episode_context: EpisodeContext | None = None,
    ) -> Chunk:
        """Create a Chunk from a list of utterances with contextual headers."""
        # Combine text
        texts = [u.get("text", "").strip() for u in utterances]
        combined_text = " ".join(texts)

        # Get timing
        start_ms = utterances[0].get("start_ms", 0)
        end_ms = utterances[-1].get("end_ms", 0)

        # Get all speakers
        speakers = list(set(u.get("speaker", "Unknown") for u in utterances))

        # Determine primary speaker (most words)
        speaker_word_counts = {}
        for utt in utterances:
            speaker = utt.get("speaker", "Unknown")
            word_count = len(utt.get("text", "").split())
            speaker_word_counts[speaker] = (
                speaker_word_counts.get(speaker, 0) + word_count
            )

        primary_speaker = max(speaker_word_counts, key=speaker_word_counts.get)

        # Build enriched text with contextual headers for embedding
        # This significantly improves retrieval by anchoring chunks to their context
        text_for_embedding = self._build_enriched_text(
            text=combined_text,
            primary_speaker=primary_speaker,
            speakers=speakers,
            episode_context=episode_context,
        )

        return Chunk(
            text=combined_text,
            text_for_embedding=text_for_embedding,
            primary_speaker=primary_speaker,
            speakers=speakers,
            start_ms=start_ms,
            end_ms=end_ms,
            chunk_index=chunk_index,
            word_count=len(combined_text.split()),
        )

    def _build_enriched_text(
        self,
        text: str,
        primary_speaker: str,
        speakers: list[str],
        episode_context: EpisodeContext | None,
    ) -> str:
        """
        Build enriched text with contextual headers for better embeddings.

        This fixes anaphora ("he", "that company") and anchors chunks
        to episode/speaker context, significantly improving retrieval.

        Format:
            Episode: <title>
            Channel: <podcast name>
            Date: <month/year>
            Speaker: <primary speaker>
            ---
            <chunk text>
        """
        if not episode_context:
            # Fallback: just add speaker context
            if primary_speaker and primary_speaker != "Unknown":
                return f"Speaker: {primary_speaker}\n---\n{text}"
            return text

        # Build header parts
        header_parts = []

        if episode_context.episode_title:
            header_parts.append(f"Episode: {episode_context.episode_title}")

        if episode_context.channel_name:
            header_parts.append(f"Channel: {episode_context.channel_name}")

        if episode_context.published_at:
            date_str = episode_context.published_at.strftime("%B %Y")
            header_parts.append(f"Date: {date_str}")

        if primary_speaker and primary_speaker != "Unknown":
            header_parts.append(f"Speaker: {primary_speaker}")
            if len(speakers) > 1:
                other_speakers = [s for s in speakers if s != primary_speaker]
                header_parts.append(f"Also speaking: {', '.join(other_speakers)}")

        # Combine header with text
        if header_parts:
            header = "\n".join(header_parts)
            return f"{header}\n---\n{text}"

        return text

    def _get_overlap_utterances(self, utterances: list[dict]) -> list[dict]:
        """Get utterances to include in overlap for next chunk."""
        if not utterances:
            return []

        # Count words from the end until we reach overlap target
        overlap_utterances = []
        word_count = 0

        for utt in reversed(utterances):
            utt_words = len(utt.get("text", "").split())
            if word_count + utt_words > self.chunk_overlap:
                break
            overlap_utterances.insert(0, utt)
            word_count += utt_words

        return overlap_utterances

    def _parse_chunk_utterances(self, chunk: Chunk) -> list[dict]:
        """
        Reconstruct utterances from a chunk.
        Note: This loses some granularity but is used for merging.
        """
        return [
            {
                "speaker": chunk.primary_speaker,
                "text": chunk.text,
                "start_ms": chunk.start_ms,
                "end_ms": chunk.end_ms,
            }
        ]
