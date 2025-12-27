import asyncio
import httpx
from pathlib import Path
from loguru import logger

from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)


class DeepgramProvider(TranscriptionProvider):
    """Deepgram transcription provider with speaker diarization."""

    BASE_URL = "https://api.deepgram.com/v1"

    def __init__(self, api_key: str, max_concurrent: int = 50):
        self._api_key = api_key
        self._max_concurrent = max_concurrent

    @property
    def name(self) -> str:
        return "deepgram"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        return True

    @property
    def cost_per_hour_cents(self) -> int:
        return 26  # $0.26/hour (Nova-2 model)

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "audio/mpeg",
        }

    async def submit_job(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> str:
        """
        Submit audio to Deepgram for transcription.

        Note: Deepgram processes synchronously by default.
        For async, we use the callback feature or just process inline.
        """
        # For simplicity, we'll use sync transcription
        # In production, you might want to use callbacks for very long files
        result = await self.transcribe(audio_path, speakers_expected, language)
        return result.provider_job_id

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """
        Deepgram processes synchronously, so this returns completed result.
        The provider_job_id is actually our local tracking ID.
        """
        # For sync processing, we don't have status checks
        # This is mainly for API compatibility
        return TranscriptResult(
            provider_job_id=provider_job_id,
            status=TranscriptionStatus.COMPLETED
        )

    async def transcribe(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> TranscriptResult:
        """Transcribe audio file using Deepgram."""
        import uuid

        logger.info(f"Starting Deepgram transcription for {audio_path}")

        # Deepgram API parameters
        params = {
            "model": "nova-2",
            "language": language,
            "diarize": "true",
            "punctuate": "true",
            "utterances": "true",
            "smart_format": "true",
        }

        job_id = str(uuid.uuid4())

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                with open(audio_path, "rb") as f:
                    audio_data = f.read()

                response = await client.post(
                    f"{self.BASE_URL}/listen",
                    headers=self._get_headers(),
                    params=params,
                    content=audio_data,
                )

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Deepgram error: {error_text}")
                    return TranscriptResult(
                        provider_job_id=job_id,
                        status=TranscriptionStatus.FAILED,
                        error_message=f"Deepgram API error: {response.status_code} - {error_text}"
                    )

                data = response.json()

        except Exception as e:
            logger.error(f"Deepgram transcription failed: {e}")
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=str(e)
            )

        # Parse response
        results = data.get("results", {})
        channels = results.get("channels", [])

        if not channels:
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message="No channels in Deepgram response"
            )

        # Get utterances with speaker labels
        utterances = []
        channel_data = channels[0]

        # Deepgram provides utterances with speaker labels
        dg_utterances = results.get("utterances", [])

        for utt in dg_utterances:
            speaker_id = utt.get("speaker", 0)
            utterances.append(Utterance(
                speaker=chr(65 + speaker_id),  # Convert 0,1,2 to A,B,C
                text=utt.get("transcript", ""),
                start_ms=int(utt.get("start", 0) * 1000),
                end_ms=int(utt.get("end", 0) * 1000),
                confidence=utt.get("confidence"),
            ))

        # Get full transcript
        alternatives = channel_data.get("alternatives", [])
        full_text = alternatives[0].get("transcript", "") if alternatives else ""

        # Duration from metadata
        metadata = data.get("metadata", {})
        duration_seconds = metadata.get("duration", 0)
        duration_ms = int(duration_seconds * 1000)

        cost_cents = self.estimate_cost(int(duration_seconds))

        logger.info(f"Deepgram transcription complete: {len(utterances)} utterances")

        return TranscriptResult(
            provider_job_id=job_id,
            status=TranscriptionStatus.COMPLETED,
            utterances=utterances,
            full_text=full_text,
            duration_ms=duration_ms,
            cost_cents=cost_cents,
            raw_response=data
        )
