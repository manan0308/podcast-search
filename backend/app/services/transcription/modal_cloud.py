"""
Modal cloud GPU transcription provider.

Uses Modal.com for serverless GPU transcription at 70-200x realtime.
Cost: ~$0.03-0.05 per hour of audio (A10G GPU pricing).
"""
import asyncio
import uuid
import json
from pathlib import Path
from typing import Optional
from loguru import logger

from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)

# Modal is optional - only load if available
try:
    import modal
    MODAL_AVAILABLE = True
except ImportError:
    MODAL_AVAILABLE = False
    logger.warning("Modal not installed, cloud GPU transcription unavailable")


# Modal app definition - only created if modal is available
if MODAL_AVAILABLE:
    # Define the Modal app
    modal_app = modal.App("podcast-search-transcriber")

    # Build the container image with all dependencies
    transcriber_image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg")
        .pip_install(
            "faster-whisper>=1.0.0",
            "torch>=2.0.0",
            "torchaudio>=2.0.0",
        )
    )

    @modal_app.cls(
        image=transcriber_image,
        gpu="A10G",  # Good balance of speed and cost
        timeout=600,
        retries=2,
        scaledown_window=60,  # Previously container_idle_timeout
    )
    class ModalWhisperTranscriber:
        """Modal class for GPU transcription."""

        @modal.enter()
        def load_model(self):
            """Load model once when container starts."""
            from faster_whisper import WhisperModel

            logger.info("Loading faster-whisper model on Modal GPU...")
            self.model = WhisperModel(
                "large-v3",
                device="cuda",
                compute_type="float16",
                num_workers=4,
            )
            logger.info("Model loaded successfully")

        @modal.method()
        def transcribe(
            self,
            audio_bytes: bytes,
            language: str = "en",
            job_id: str = None
        ) -> dict:
            """Transcribe audio bytes on GPU."""
            import tempfile
            from pathlib import Path

            # Write audio to temp file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                audio_path = f.name

            try:
                segments, info = self.model.transcribe(
                    audio_path,
                    language=language if language else None,
                    task="transcribe",
                    vad_filter=True,
                    word_timestamps=True,
                    temperature=0.0,
                    beam_size=5,
                )

                # Process segments
                utterances = []
                full_text_parts = []

                for segment in segments:
                    text = segment.text.strip()
                    if text:
                        utterances.append({
                            "speaker": "A",
                            "text": text,
                            "start_ms": int(segment.start * 1000),
                            "end_ms": int(segment.end * 1000),
                            "confidence": segment.avg_logprob if hasattr(segment, 'avg_logprob') else None,
                        })
                        full_text_parts.append(text)

                return {
                    "status": "completed",
                    "job_id": job_id,
                    "utterances": utterances,
                    "full_text": " ".join(full_text_parts),
                    "duration_ms": int(info.duration * 1000),
                    "language": info.language,
                    "language_probability": info.language_probability,
                }

            except Exception as e:
                return {
                    "status": "failed",
                    "job_id": job_id,
                    "error": str(e),
                }
            finally:
                # Cleanup temp file
                Path(audio_path).unlink(missing_ok=True)


class ModalCloudProvider(TranscriptionProvider):
    """
    Cloud GPU transcription using Modal.

    Provides 70-200x realtime transcription speed on cloud GPUs.
    Cost-effective for batches (GPU spins up once, processes many files).

    Requires:
    - modal package
    - MODAL_TOKEN_ID and MODAL_TOKEN_SECRET env vars
    """

    # Approximate cost: A10G is ~$1.10/hr, processes ~100hrs of audio/hr
    # So cost is roughly $0.011/hr of audio, we'll estimate $0.03 with overhead
    COST_PER_HOUR_CENTS = 3

    def __init__(
        self,
        model: str = "large-v3",
        gpu_type: str = "A10G",
        max_concurrent: int = 10,
    ):
        """
        Initialize Modal cloud provider.

        Args:
            model: Whisper model to use
            gpu_type: Modal GPU type (T4, A10G, A100)
            max_concurrent: Max parallel jobs (Modal handles scaling)
        """
        self._model_name = model
        self._gpu_type = gpu_type
        self._max_concurrent = max_concurrent
        self._transcriber = None

    @property
    def name(self) -> str:
        return "modal-cloud"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        return False  # Not implemented for cloud yet

    @property
    def cost_per_hour_cents(self) -> int:
        return self.COST_PER_HOUR_CENTS

    def _check_modal_available(self):
        """Check if Modal is available and configured."""
        if not MODAL_AVAILABLE:
            raise RuntimeError(
                "Modal not installed. Run: pip install modal"
            )

        import os
        if not os.environ.get("MODAL_TOKEN_ID"):
            raise RuntimeError(
                "MODAL_TOKEN_ID not set. Run: modal token new"
            )

    def _get_transcriber(self):
        """Get or create Modal transcriber instance."""
        if self._transcriber is None:
            self._check_modal_available()
            self._transcriber = ModalWhisperTranscriber()
        return self._transcriber

    async def submit_job(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> str:
        """Submit audio for Modal cloud transcription."""
        job_id = str(uuid.uuid4())
        return job_id

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """Modal processes synchronously, status always completed."""
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
        """Transcribe audio using Modal cloud GPU."""
        job_id = str(uuid.uuid4())
        logger.info(f"Starting Modal cloud transcription for {audio_path}")

        try:
            self._check_modal_available()

            # Read audio file
            audio_bytes = audio_path.read_bytes()
            audio_size_mb = len(audio_bytes) / (1024 * 1024)
            logger.info(f"Uploading {audio_size_mb:.1f}MB audio to Modal")

            # Run transcription on Modal (this handles the remote call)
            loop = asyncio.get_event_loop()
            transcriber = self._get_transcriber()

            result = await loop.run_in_executor(
                None,
                lambda: transcriber.transcribe.remote(
                    audio_bytes=audio_bytes,
                    language=language,
                    job_id=job_id,
                )
            )

            if result.get("status") == "failed":
                return TranscriptResult(
                    provider_job_id=job_id,
                    status=TranscriptionStatus.FAILED,
                    error_message=result.get("error", "Unknown error")
                )

            # Convert utterance dicts to Utterance objects
            utterances = [
                Utterance(
                    speaker=u["speaker"],
                    text=u["text"],
                    start_ms=u["start_ms"],
                    end_ms=u["end_ms"],
                    confidence=u.get("confidence"),
                )
                for u in result.get("utterances", [])
            ]

            # Estimate cost
            duration_hours = result.get("duration_ms", 0) / 1000 / 3600
            estimated_cost = int(duration_hours * self.COST_PER_HOUR_CENTS)

            logger.info(
                f"Modal cloud transcription complete: "
                f"{len(utterances)} utterances, "
                f"{result.get('duration_ms', 0) / 1000:.1f}s audio, "
                f"~${estimated_cost/100:.3f} cost"
            )

            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.COMPLETED,
                utterances=utterances,
                full_text=result.get("full_text", ""),
                duration_ms=result.get("duration_ms"),
                cost_cents=estimated_cost,
                raw_response={
                    "language": result.get("language"),
                    "language_probability": result.get("language_probability"),
                    "gpu_type": self._gpu_type,
                }
            )

        except Exception as e:
            logger.error(f"Modal cloud transcription failed: {e}")
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=str(e)
            )

    async def transcribe_batch(
        self,
        audio_paths: list[Path],
        language: str = "en"
    ) -> list[TranscriptResult]:
        """
        Transcribe multiple files in parallel on Modal.

        This is the most cost-effective way to use Modal - the GPU container
        stays warm and processes all files efficiently.
        """
        logger.info(f"Starting batch transcription of {len(audio_paths)} files on Modal")

        self._check_modal_available()
        transcriber = self._get_transcriber()

        # Prepare all audio data
        batch_data = []
        for i, path in enumerate(audio_paths):
            batch_data.append({
                "audio_bytes": path.read_bytes(),
                "language": language,
                "job_id": str(uuid.uuid4()),
            })

        # Run all transcriptions in parallel using Modal's map
        loop = asyncio.get_event_loop()

        results = await loop.run_in_executor(
            None,
            lambda: list(transcriber.transcribe.map(
                [d["audio_bytes"] for d in batch_data],
                kwargs={
                    "language": language,
                }
            ))
        )

        # Convert results
        transcript_results = []
        for i, result in enumerate(results):
            if result.get("status") == "failed":
                transcript_results.append(TranscriptResult(
                    provider_job_id=batch_data[i]["job_id"],
                    status=TranscriptionStatus.FAILED,
                    error_message=result.get("error", "Unknown error")
                ))
            else:
                utterances = [
                    Utterance(
                        speaker=u["speaker"],
                        text=u["text"],
                        start_ms=u["start_ms"],
                        end_ms=u["end_ms"],
                        confidence=u.get("confidence"),
                    )
                    for u in result.get("utterances", [])
                ]

                duration_hours = result.get("duration_ms", 0) / 1000 / 3600
                estimated_cost = int(duration_hours * self.COST_PER_HOUR_CENTS)

                transcript_results.append(TranscriptResult(
                    provider_job_id=batch_data[i]["job_id"],
                    status=TranscriptionStatus.COMPLETED,
                    utterances=utterances,
                    full_text=result.get("full_text", ""),
                    duration_ms=result.get("duration_ms"),
                    cost_cents=estimated_cost,
                ))

        logger.info(f"Batch transcription complete: {len(transcript_results)} results")
        return transcript_results


# For direct Modal CLI deployment: modal deploy modal_cloud.py
if MODAL_AVAILABLE:
    app = modal_app
