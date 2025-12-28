import json
from loguru import logger
import anthropic

from app.config import settings
from app.services.transcription.base import Utterance


class SpeakerLabelingService:
    """
    Use Claude to identify speakers in podcast transcripts.

    Maps generic speaker labels (A, B, C) to actual names (Sam Parr, Shaan Puri, Guest).
    """

    def __init__(self):
        # Use async client to avoid blocking the event loop
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    async def identify_speakers(
        self,
        utterances: list[Utterance],
        known_speakers: list[str],
        sample_size: int = 30,
        episode_title: str | None = None,
    ) -> dict[str, str]:
        """
        Identify which speaker label corresponds to which person.

        Args:
            utterances: List of utterances with speaker labels (A, B, C, etc.)
            known_speakers: List of known host names ["Sam Parr", "Shaan Puri"]
            sample_size: Number of utterances to sample for identification
            episode_title: Optional episode title for context

        Returns:
            Mapping of speaker labels to names: {"A": "Sam Parr", "B": "Shaan Puri", "C": "Guest"}
        """
        if not utterances:
            return {}

        # Get unique speakers
        unique_speakers = list(set(u.speaker for u in utterances))

        if len(unique_speakers) == 1:
            # Only one speaker detected - could be an interview or solo episode
            return {unique_speakers[0]: known_speakers[0] if known_speakers else "Host"}

        # Sample utterances for context
        sample = self._get_representative_sample(utterances, sample_size)

        # Build prompt
        prompt = self._build_identification_prompt(
            sample=sample,
            unique_speakers=unique_speakers,
            known_speakers=known_speakers,
            episode_title=episode_title,
        )

        logger.info(f"Identifying {len(unique_speakers)} speakers using Claude")

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text

            # Parse JSON response
            mapping = self._parse_response(content, unique_speakers, known_speakers)

            logger.info(f"Speaker mapping: {mapping}")
            return mapping

        except Exception as e:
            logger.error(f"Speaker identification failed: {e}")
            # Fallback: assign known speakers in order, rest as Guest
            return self._fallback_mapping(unique_speakers, known_speakers)

    def apply_speaker_labels(
        self,
        utterances: list[Utterance],
        speaker_mapping: dict[str, str],
        default_label: str = "Guest",
    ) -> list[dict]:
        """
        Apply identified speaker names to utterances.

        Args:
            utterances: List of utterances with raw speaker labels
            speaker_mapping: Mapping from raw labels to names
            default_label: Label for unknown speakers

        Returns:
            List of utterance dicts with speaker names applied
        """
        guest_counter = 0
        guest_mapping = {}  # Track unknown speakers to give consistent labels

        result = []
        for utt in utterances:
            raw_speaker = utt.speaker

            if raw_speaker in speaker_mapping:
                speaker_name = speaker_mapping[raw_speaker]
            else:
                # Unknown speaker - assign Guest label
                if raw_speaker not in guest_mapping:
                    guest_counter += 1
                    if guest_counter == 1:
                        guest_mapping[raw_speaker] = default_label
                    else:
                        guest_mapping[raw_speaker] = f"{default_label} {guest_counter}"
                speaker_name = guest_mapping[raw_speaker]

            result.append({
                "speaker": speaker_name,
                "speaker_raw": raw_speaker,
                "text": utt.text,
                "start_ms": utt.start_ms,
                "end_ms": utt.end_ms,
                "confidence": utt.confidence,
            })

        return result

    def _get_representative_sample(
        self,
        utterances: list[Utterance],
        sample_size: int
    ) -> list[Utterance]:
        """Get a representative sample of utterances from different parts of the episode."""
        if len(utterances) <= sample_size:
            return utterances

        # Sample from beginning, middle, and end
        section_size = sample_size // 3
        beginning = utterances[:section_size]
        middle_start = len(utterances) // 2 - section_size // 2
        middle = utterances[middle_start:middle_start + section_size]
        end = utterances[-section_size:]

        return beginning + middle + end

    def _build_identification_prompt(
        self,
        sample: list[Utterance],
        unique_speakers: list[str],
        known_speakers: list[str],
        episode_title: str | None,
    ) -> str:
        """Build the Claude prompt for speaker identification."""
        # Format sample utterances
        sample_text = "\n".join([
            f"[{u.speaker}]: {u.text[:200]}{'...' if len(u.text) > 200 else ''}"
            for u in sample
        ])

        # Build speaker descriptions if we know them
        speaker_hints = ""
        if known_speakers:
            speaker_hints = f"""
Known hosts of this podcast:
{chr(10).join(f'- {s}' for s in known_speakers)}

Identification hints:
- Listen for personal references (e.g., "I built Hampton" likely = Sam Parr)
- Listen for names mentioned (e.g., "Sam, what do you think?" helps identify Sam)
- Consider speaking patterns and topics they're known for
"""

        prompt = f"""Analyze this podcast transcript and identify which speaker label (A, B, C, etc.) corresponds to which person.

{f'Episode Title: {episode_title}' if episode_title else ''}
{speaker_hints}

Speaker labels found: {', '.join(unique_speakers)}

Transcript sample:
---
{sample_text}
---

Based on the content, speaking patterns, and any names/references mentioned, create a mapping from speaker labels to names.

Return your answer as a JSON object mapping speaker labels to names.
For speakers you cannot identify, use "Guest" (or "Guest 2", "Guest 3" for multiple unknown speakers).

Example response format:
{{"A": "Sam Parr", "B": "Shaan Puri", "C": "Guest"}}

Important:
- Only use names from the known hosts list if you're confident
- If unsure, use "Guest" rather than guessing wrong
- Return ONLY the JSON object, no other text
"""
        return prompt

    def _parse_response(
        self,
        response: str,
        unique_speakers: list[str],
        known_speakers: list[str],
    ) -> dict[str, str]:
        """Parse Claude's response into a speaker mapping."""
        # Try to extract JSON from response
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])

        try:
            mapping = json.loads(response)

            # Validate mapping
            if not isinstance(mapping, dict):
                raise ValueError("Response is not a dict")

            # Ensure all unique speakers are mapped
            for speaker in unique_speakers:
                if speaker not in mapping:
                    mapping[speaker] = "Guest"

            return mapping

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse speaker mapping: {e}")
            return self._fallback_mapping(unique_speakers, known_speakers)

    def _fallback_mapping(
        self,
        unique_speakers: list[str],
        known_speakers: list[str],
    ) -> dict[str, str]:
        """Create a fallback mapping when identification fails."""
        mapping = {}
        sorted_speakers = sorted(unique_speakers)

        for i, speaker in enumerate(sorted_speakers):
            if i < len(known_speakers):
                mapping[speaker] = known_speakers[i]
            elif i == len(known_speakers):
                mapping[speaker] = "Guest"
            else:
                mapping[speaker] = f"Guest {i - len(known_speakers) + 1}"

        return mapping
