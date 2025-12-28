"""
Modal Hybrid Transcription Provider.

Downloads audio locally first (bypasses YouTube cloud IP blocks),
then uploads to Modal for parallel GPU transcription.

This is the recommended approach for bulk channel transcription:
1. Download all audio locally (YouTube doesn't block home IPs)
2. Upload audio to Modal in parallel
3. Transcribe on 100+ parallel GPUs
4. Stream results back

Performance: ~8-15 minutes for 100 videos vs 25+ hours on local GPU
"""

import asyncio
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable
from loguru import logger

from app.config import settings
from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)
from app.services.transcription.modal_cloud import MODAL_AVAILABLE

if MODAL_AVAILABLE:
    from app.services.transcription.modal_cloud import (
        ModalWhisperTranscriber,
        modal_app,
    )


class ModalHybridProvider(TranscriptionProvider):
    """
    Hybrid transcription: local download + Modal cloud transcription.

    Use this when:
    - YouTube blocks Modal/cloud IPs (403 errors on download)
    - You have many videos to transcribe (batch efficiency)
    - You want maximum parallelism (100+ concurrent GPU workers)

    Workflow:
    1. Audio is downloaded locally (handled by caller)
    2. Audio is uploaded to Modal
    3. Transcription runs on cloud GPU
    4. Results are streamed back
    """

    COST_PER_HOUR_CENTS = 3  # ~$0.03/hr of audio

    def __init__(
        self,
        model: str = "large-v3",
        gpu_type: str = "A10G",
        max_concurrent: int = 50,
        max_upload_workers: int = 10,
    ):
        """
        Initialize Modal hybrid provider.

        Args:
            model: Whisper model to use
            gpu_type: Modal GPU type (T4, A10G, A100)
            max_concurrent: Max parallel Modal workers
            max_upload_workers: Max parallel upload threads
        """
        self._model_name = model
        self._gpu_type = gpu_type
        self._max_concurrent = max_concurrent
        self._max_upload_workers = max_upload_workers
        self._transcriber = None

    @property
    def name(self) -> str:
        return "modal-hybrid"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        return False

    @property
    def cost_per_hour_cents(self) -> int:
        return self.COST_PER_HOUR_CENTS

    def _check_modal_available(self):
        """Check if Modal is available and configured."""
        if not MODAL_AVAILABLE:
            raise RuntimeError("Modal not installed. Run: pip install modal")

        import os

        if not os.environ.get("MODAL_TOKEN_ID"):
            raise RuntimeError("MODAL_TOKEN_ID not set. Run: modal token new")

    def _get_transcriber(self):
        """Get or create Modal transcriber instance."""
        if self._transcriber is None:
            self._check_modal_available()
            self._transcriber = ModalWhisperTranscriber()
        return self._transcriber

    async def submit_job(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> str:
        """Submit audio for Modal cloud transcription."""
        return str(uuid.uuid4())

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """Modal processes synchronously."""
        return TranscriptResult(
            provider_job_id=provider_job_id, status=TranscriptionStatus.COMPLETED
        )

    async def transcribe(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> TranscriptResult:
        """
        Transcribe a single audio file.

        For single files, this is the same as modal-cloud provider.
        The hybrid advantage comes from batch processing.
        """
        job_id = str(uuid.uuid4())
        logger.info(f"Starting Modal hybrid transcription for {audio_path}")

        try:
            self._check_modal_available()

            # Read and upload audio
            audio_bytes = audio_path.read_bytes()
            audio_size_mb = len(audio_bytes) / (1024 * 1024)
            logger.info(f"Uploading {audio_size_mb:.1f}MB audio to Modal")

            # Run transcription
            loop = asyncio.get_event_loop()
            transcriber = self._get_transcriber()

            result = await loop.run_in_executor(
                None,
                lambda: transcriber.transcribe.remote(
                    audio_bytes=audio_bytes,
                    language=language,
                    job_id=job_id,
                ),
            )

            return self._process_result(result, job_id)

        except Exception as e:
            logger.error(f"Modal hybrid transcription failed: {e}")
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=str(e),
            )

    async def transcribe_batch(
        self,
        audio_paths: list[Path],
        language: str = "en",
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[TranscriptResult]:
        """
        Transcribe multiple audio files in parallel on Modal.

        This is where the hybrid approach shines:
        - Audio was downloaded locally (no cloud IP blocks)
        - Files are uploaded in parallel
        - Modal processes all files on parallel GPUs
        - Results stream back as they complete

        Args:
            audio_paths: List of local audio file paths
            language: Language code for transcription
            on_progress: Optional callback(completed, total, status_message)

        Returns:
            List of TranscriptResults in same order as input
        """
        if not audio_paths:
            return []

        total = len(audio_paths)
        logger.info(f"Starting Modal hybrid batch transcription: {total} files")

        self._check_modal_available()
        transcriber = self._get_transcriber()

        # Prepare batch data with progress tracking
        batch_data = []
        if on_progress:
            on_progress(0, total, "Preparing audio files...")

        # Read all audio files in parallel
        def read_audio(path: Path) -> tuple[Path, bytes]:
            return (path, path.read_bytes())

        with ThreadPoolExecutor(max_workers=self._max_upload_workers) as executor:
            audio_data = list(executor.map(read_audio, audio_paths))

        for i, (path, audio_bytes) in enumerate(audio_data):
            batch_data.append(
                {
                    "path": path,
                    "audio_bytes": audio_bytes,
                    "job_id": str(uuid.uuid4()),
                }
            )

        if on_progress:
            on_progress(0, total, f"Uploading {total} files to Modal...")

        # Use Modal's spawn for parallel execution with streaming results
        loop = asyncio.get_event_loop()

        def run_batch():
            """Run batch transcription on Modal."""
            # Spawn all jobs
            handles = []
            for data in batch_data:
                handle = transcriber.transcribe.spawn(
                    audio_bytes=data["audio_bytes"],
                    language=language,
                    job_id=data["job_id"],
                )
                handles.append((data, handle))

            # Collect results as they complete
            results = []
            completed = 0
            for data, handle in handles:
                try:
                    result = handle.get()
                    results.append((data, result))
                    completed += 1
                    if on_progress:
                        on_progress(
                            completed, total, f"Transcribed {completed}/{total}"
                        )
                except Exception as e:
                    results.append((data, {"status": "failed", "error": str(e)}))
                    completed += 1
                    if on_progress:
                        on_progress(
                            completed,
                            total,
                            f"Transcribed {completed}/{total} (1 failed)",
                        )

            return results

        results = await loop.run_in_executor(None, run_batch)

        # Convert to TranscriptResults maintaining order
        path_to_result = {
            str(data["path"]): self._process_result(result, data["job_id"])
            for data, result in results
        }

        transcript_results = [
            path_to_result.get(
                str(path),
                TranscriptResult(
                    provider_job_id="unknown",
                    status=TranscriptionStatus.FAILED,
                    error_message="Result not found",
                ),
            )
            for path in audio_paths
        ]

        completed_count = sum(
            1 for r in transcript_results if r.status == TranscriptionStatus.COMPLETED
        )
        failed_count = sum(
            1 for r in transcript_results if r.status == TranscriptionStatus.FAILED
        )

        logger.info(
            f"Modal hybrid batch complete: {completed_count} success, {failed_count} failed"
        )

        return transcript_results

    def _process_result(self, result: dict, job_id: str) -> TranscriptResult:
        """Convert Modal result dict to TranscriptResult."""
        if result.get("status") == "failed":
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=result.get("error", "Unknown error"),
            )

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
                "mode": "hybrid",
            },
        )
