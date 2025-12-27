import asyncio
from pathlib import Path
import assemblyai as aai
from loguru import logger

from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)


class AssemblyAIProvider(TranscriptionProvider):
    """AssemblyAI transcription provider with speaker diarization."""

    def __init__(self, api_key: str, max_concurrent: int = 32):
        self._api_key = api_key
        self._max_concurrent = max_concurrent
        aai.settings.api_key = api_key
        self._transcriber = aai.Transcriber()

    @property
    def name(self) -> str:
        return "assemblyai"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        return True

    @property
    def cost_per_hour_cents(self) -> int:
        return 37  # $0.37/hour

    async def submit_job(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> str:
        """Submit audio to AssemblyAI for transcription."""
        logger.info(f"Submitting {audio_path} to AssemblyAI")

        config = aai.TranscriptionConfig(
            speaker_labels=True,
            speakers_expected=speakers_expected,
            language_code=language,
        )

        # Run in thread pool since assemblyai SDK is sync
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None,
            lambda: self._transcriber.submit(str(audio_path), config=config)
        )

        logger.info(f"AssemblyAI job submitted: {transcript.id}")
        return transcript.id

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """Check status of AssemblyAI transcription job."""
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None,
            lambda: aai.Transcript.get_by_id(provider_job_id)
        )

        # Map AssemblyAI status to our status
        status_map = {
            "queued": TranscriptionStatus.PENDING,
            "processing": TranscriptionStatus.PROCESSING,
            "completed": TranscriptionStatus.COMPLETED,
            "error": TranscriptionStatus.FAILED,
        }

        status = status_map.get(transcript.status, TranscriptionStatus.PENDING)

        if status == TranscriptionStatus.FAILED:
            return TranscriptResult(
                provider_job_id=provider_job_id,
                status=status,
                error_message=transcript.error or "Unknown error"
            )

        if status != TranscriptionStatus.COMPLETED:
            return TranscriptResult(
                provider_job_id=provider_job_id,
                status=status
            )

        # Parse completed transcript
        utterances = []
        if transcript.utterances:
            for utt in transcript.utterances:
                utterances.append(Utterance(
                    speaker=utt.speaker,
                    text=utt.text,
                    start_ms=utt.start,
                    end_ms=utt.end,
                    confidence=utt.confidence,
                ))

        # Calculate cost
        duration_ms = transcript.audio_duration * 1000 if transcript.audio_duration else 0
        cost_cents = self.estimate_cost(int(duration_ms / 1000))

        return TranscriptResult(
            provider_job_id=provider_job_id,
            status=status,
            utterances=utterances,
            full_text=transcript.text,
            duration_ms=int(duration_ms),
            cost_cents=cost_cents,
            raw_response={
                "id": transcript.id,
                "status": transcript.status,
                "audio_duration": transcript.audio_duration,
                "confidence": transcript.confidence,
            }
        )

    async def transcribe(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> TranscriptResult:
        """Transcribe audio file and wait for result."""
        logger.info(f"Starting AssemblyAI transcription for {audio_path}")

        config = aai.TranscriptionConfig(
            speaker_labels=True,
            speakers_expected=speakers_expected,
            language_code=language,
        )

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None,
            lambda: self._transcriber.transcribe(str(audio_path), config=config)
        )

        if transcript.status == "error":
            return TranscriptResult(
                provider_job_id=transcript.id,
                status=TranscriptionStatus.FAILED,
                error_message=transcript.error or "Unknown error"
            )

        # Parse utterances
        utterances = []
        if transcript.utterances:
            for utt in transcript.utterances:
                utterances.append(Utterance(
                    speaker=utt.speaker,
                    text=utt.text,
                    start_ms=utt.start,
                    end_ms=utt.end,
                    confidence=utt.confidence,
                ))

        duration_ms = transcript.audio_duration * 1000 if transcript.audio_duration else 0
        cost_cents = self.estimate_cost(int(duration_ms / 1000))

        logger.info(f"AssemblyAI transcription complete: {len(utterances)} utterances")

        return TranscriptResult(
            provider_job_id=transcript.id,
            status=TranscriptionStatus.COMPLETED,
            utterances=utterances,
            full_text=transcript.text,
            duration_ms=int(duration_ms),
            cost_cents=cost_cents,
            raw_response={
                "id": transcript.id,
                "status": transcript.status,
                "audio_duration": transcript.audio_duration,
                "confidence": transcript.confidence,
            }
        )
