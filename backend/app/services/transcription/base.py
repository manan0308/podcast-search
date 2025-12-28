from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import asyncio


class TranscriptionStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Utterance:
    """A single speaker utterance from transcription."""

    speaker: str  # "A", "B", "C" (raw from provider)
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None
    words: list[dict] | None = None  # Word-level timing if available


@dataclass
class TranscriptResult:
    """Result of a transcription job."""

    provider_job_id: str
    status: TranscriptionStatus
    utterances: list[Utterance] | None = None
    full_text: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    cost_cents: int | None = None
    raw_response: dict | None = field(default=None, repr=False)


class TranscriptionProvider(ABC):
    """Abstract base class for transcription providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name: 'assemblyai', 'deepgram', 'whisper'."""
        pass

    @property
    @abstractmethod
    def max_concurrent_jobs(self) -> int:
        """Maximum concurrent transcription jobs."""
        pass

    @property
    @abstractmethod
    def supports_diarization(self) -> bool:
        """Whether provider supports speaker diarization."""
        pass

    @property
    @abstractmethod
    def cost_per_hour_cents(self) -> int:
        """Cost per hour of audio in cents."""
        pass

    @abstractmethod
    async def submit_job(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> str:
        """
        Submit audio for transcription.
        Returns provider_job_id for tracking.
        """
        pass

    @abstractmethod
    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """Check status of a transcription job."""
        pass

    async def wait_for_completion(
        self,
        provider_job_id: str,
        initial_poll_interval: float = 5.0,
        max_poll_interval: float = 30.0,
        timeout: float = 3600.0,
    ) -> TranscriptResult:
        """Wait for job to complete with exponential backoff polling."""
        elapsed = 0.0
        poll_interval = initial_poll_interval

        while elapsed < timeout:
            result = await self.get_status(provider_job_id)

            if result.status == TranscriptionStatus.COMPLETED:
                return result

            if result.status == TranscriptionStatus.FAILED:
                return result

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            # Exponential backoff: increase interval by 1.5x, capped at max
            poll_interval = min(poll_interval * 1.5, max_poll_interval)

        return TranscriptResult(
            provider_job_id=provider_job_id,
            status=TranscriptionStatus.FAILED,
            error_message=f"Transcription timed out after {timeout} seconds",
        )

    async def transcribe(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> TranscriptResult:
        """
        Convenience method: submit and wait for completion.
        """
        job_id = await self.submit_job(audio_path, speakers_expected, language)
        return await self.wait_for_completion(job_id)

    def estimate_cost(self, duration_seconds: int) -> int:
        """Estimate cost in cents for given audio duration."""
        hours = duration_seconds / 3600
        return int(hours * self.cost_per_hour_cents)
