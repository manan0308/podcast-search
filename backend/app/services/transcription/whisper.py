import asyncio
import uuid
from pathlib import Path
from loguru import logger

from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)


class WhisperProvider(TranscriptionProvider):
    """
    Local Whisper transcription provider.

    Requires:
    - openai-whisper
    - torch
    - For diarization: pyannote.audio (optional)
    """

    def __init__(
        self,
        model: str = "large-v3",
        device: str = "cuda",
        max_concurrent: int = 2
    ):
        self._model_name = model
        self._device = device
        self._max_concurrent = max_concurrent
        self._model = None
        self._diarization_pipeline = None

    @property
    def name(self) -> str:
        return "whisper"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        # Whisper doesn't natively support diarization
        # We use pyannote for this if available
        try:
            import pyannote.audio
            return True
        except ImportError:
            return False

    @property
    def cost_per_hour_cents(self) -> int:
        return 0  # Free (local processing)

    def _load_model(self):
        """Lazy load Whisper model."""
        if self._model is None:
            try:
                import whisper
                logger.info(f"Loading Whisper model: {self._model_name}")
                self._model = whisper.load_model(self._model_name, device=self._device)
                logger.info("Whisper model loaded")
            except ImportError:
                raise RuntimeError("whisper not installed. Run: pip install openai-whisper")
        return self._model

    def _load_diarization(self):
        """Lazy load pyannote diarization pipeline."""
        if self._diarization_pipeline is None:
            try:
                from pyannote.audio import Pipeline
                import os

                hf_token = os.environ.get("HF_TOKEN")
                if not hf_token:
                    logger.warning("HF_TOKEN not set, diarization may fail")

                self._diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=hf_token
                )

                if self._device == "cuda":
                    import torch
                    self._diarization_pipeline.to(torch.device("cuda"))

            except ImportError:
                logger.warning("pyannote.audio not installed, diarization disabled")
                return None
            except Exception as e:
                logger.warning(f"Failed to load diarization pipeline: {e}")
                return None

        return self._diarization_pipeline

    async def submit_job(
        self,
        audio_path: Path,
        speakers_expected: int = 2,
        language: str = "en"
    ) -> str:
        """Submit audio for local Whisper transcription."""
        # For local processing, we just generate an ID
        # The actual transcription happens in transcribe()
        job_id = str(uuid.uuid4())
        return job_id

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """
        Local Whisper processes synchronously.
        Status checks are not really applicable.
        """
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
        """Transcribe audio using local Whisper."""
        job_id = str(uuid.uuid4())
        logger.info(f"Starting Whisper transcription for {audio_path}")

        try:
            # Run CPU-intensive transcription in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._transcribe_sync(audio_path, language)
            )

            # Try diarization if available
            if self.supports_diarization:
                diarization_result = await loop.run_in_executor(
                    None,
                    lambda: self._diarize_sync(audio_path, result)
                )
                if diarization_result:
                    result = diarization_result

            # Get audio duration safely
            duration_ms = await self._get_audio_duration_safe(audio_path)

            logger.info(f"Whisper transcription complete: {len(result['utterances'])} utterances")

            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.COMPLETED,
                utterances=result["utterances"],
                full_text=result["full_text"],
                duration_ms=duration_ms,
                cost_cents=0,
                raw_response=result.get("raw")
            )

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=str(e)
            )

    def _transcribe_sync(self, audio_path: Path, language: str) -> dict:
        """Synchronous Whisper transcription."""
        model = self._load_model()

        result = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            verbose=False
        )

        # Without diarization, all text is from "Speaker A"
        utterances = []
        full_text = result.get("text", "")

        # Group by segments
        for segment in result.get("segments", []):
            utterances.append(Utterance(
                speaker="A",  # Single speaker without diarization
                text=segment.get("text", "").strip(),
                start_ms=int(segment.get("start", 0) * 1000),
                end_ms=int(segment.get("end", 0) * 1000),
                confidence=None,
            ))

        return {
            "utterances": utterances,
            "full_text": full_text,
            "raw": result
        }

    def _diarize_sync(self, audio_path: Path, whisper_result: dict) -> dict | None:
        """Apply speaker diarization to Whisper results."""
        pipeline = self._load_diarization()
        if pipeline is None:
            return None

        try:
            diarization = pipeline(str(audio_path))

            # Map whisper segments to speakers
            utterances = []

            for segment in whisper_result.get("raw", {}).get("segments", []):
                seg_start = segment.get("start", 0)
                seg_end = segment.get("end", 0)
                seg_mid = (seg_start + seg_end) / 2

                # Find which speaker is talking at the midpoint
                speaker = "A"
                for turn, _, spk in diarization.itertracks(yield_label=True):
                    if turn.start <= seg_mid <= turn.end:
                        # Convert SPEAKER_00 to A, SPEAKER_01 to B, etc.
                        try:
                            spk_num = int(spk.split("_")[-1])
                            speaker = chr(65 + spk_num)
                        except (ValueError, IndexError):
                            speaker = spk
                        break

                utterances.append(Utterance(
                    speaker=speaker,
                    text=segment.get("text", "").strip(),
                    start_ms=int(seg_start * 1000),
                    end_ms=int(seg_end * 1000),
                    confidence=None,
                ))

            return {
                "utterances": utterances,
                "full_text": whisper_result["full_text"],
                "raw": whisper_result.get("raw")
            }

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return None

    async def _get_audio_duration_safe(self, audio_path: Path) -> int:
        """
        Get audio duration safely without command injection risk.

        Validates the path is within expected directories and uses
        subprocess with list args (not shell) to prevent injection.
        """
        import subprocess
        import os
        from app.config import settings

        # Validate path is a real file
        if not audio_path.exists():
            logger.warning(f"Audio file not found: {audio_path}")
            return 0

        # Validate path is within allowed directories
        try:
            resolved = audio_path.resolve()
            audio_dir = Path(settings.AUDIO_DIR).resolve()

            # Check path is under audio directory or /tmp
            if not (str(resolved).startswith(str(audio_dir)) or
                    str(resolved).startswith("/tmp") or
                    str(resolved).startswith("/var/folders")):
                logger.error(f"Audio path outside allowed directory: {resolved}")
                return 0
        except Exception as e:
            logger.error(f"Path validation failed: {e}")
            return 0

        # Validate filename contains only safe characters
        import re
        filename = audio_path.name
        if not re.match(r'^[\w\-\.]+$', filename):
            logger.error(f"Unsafe characters in filename: {filename}")
            return 0

        try:
            # Use subprocess with list args (no shell=True) - safe from injection
            duration_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(resolved)],
                capture_output=True,
                text=True,
                timeout=30,  # Timeout protection
            )
            duration_seconds = float(duration_result.stdout.strip()) if duration_result.stdout else 0
            return int(duration_seconds * 1000)
        except subprocess.TimeoutExpired:
            logger.error("ffprobe timed out")
            return 0
        except (ValueError, subprocess.SubprocessError) as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 0
