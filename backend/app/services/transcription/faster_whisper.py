"""
Faster-Whisper transcription provider.

Uses CTranslate2 for 4x faster inference than OpenAI Whisper.
- GPU: float16 compute (35-40x realtime)
- CPU: int8 compute (~4x realtime)
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional
from loguru import logger

from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionStatus,
    Utterance,
    TranscriptResult,
)


class FasterWhisperProvider(TranscriptionProvider):
    """
    High-performance local transcription using faster-whisper.

    faster-whisper is a reimplementation of OpenAI's Whisper using CTranslate2,
    providing up to 4x faster transcription with similar accuracy.

    Requires:
    - faster-whisper
    - For GPU: CUDA toolkit
    - For diarization: pyannote.audio (optional)
    """

    def __init__(
        self,
        model: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
        max_concurrent: int = 2,
        num_workers: int = 4,
    ):
        """
        Initialize faster-whisper provider.

        Args:
            model: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to use ("cuda", "cpu", or "auto")
            compute_type: Compute precision ("float16", "int8", "int8_float16", "auto")
            max_concurrent: Maximum concurrent transcription jobs
            num_workers: Number of CPU workers for preprocessing
        """
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._max_concurrent = max_concurrent
        self._num_workers = num_workers
        self._model = None
        self._diarization_pipeline = None

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def max_concurrent_jobs(self) -> int:
        return self._max_concurrent

    @property
    def supports_diarization(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("pyannote.audio") is not None
        except ImportError:
            return False

    @property
    def cost_per_hour_cents(self) -> int:
        return 0  # Free (local processing)

    def _detect_device_and_compute(self) -> tuple[str, str]:
        """Auto-detect optimal device and compute type."""
        device = self._device
        compute_type = self._compute_type

        if device == "auto":
            try:
                import torch

                if torch.cuda.is_available():
                    device = "cuda"
                    logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
                else:
                    device = "cpu"
                    logger.info("CUDA not available, using CPU")
            except ImportError:
                device = "cpu"
                logger.info("PyTorch not installed, using CPU")

        if compute_type == "auto":
            if device == "cuda":
                compute_type = "float16"  # Best for GPU
            else:
                compute_type = "int8"  # Best for CPU

        return device, compute_type

    def _load_model(self):
        """Lazy load faster-whisper model."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise RuntimeError(
                    "faster-whisper not installed. Run: pip install faster-whisper"
                )

            device, compute_type = self._detect_device_and_compute()

            logger.info(
                f"Loading faster-whisper model: {self._model_name} "
                f"(device={device}, compute_type={compute_type})"
            )

            try:
                self._model = WhisperModel(
                    self._model_name,
                    device=device,
                    compute_type=compute_type,
                    num_workers=self._num_workers,
                )
                logger.info("Faster-whisper model loaded successfully")
            except Exception as e:
                # Fallback to CPU if GPU fails
                if device == "cuda":
                    logger.warning(
                        f"GPU initialization failed: {e}, falling back to CPU"
                    )
                    self._model = WhisperModel(
                        self._model_name,
                        device="cpu",
                        compute_type="int8",
                        num_workers=self._num_workers,
                    )
                    logger.info("Faster-whisper model loaded on CPU")
                else:
                    raise

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
                    return None

                logger.info("Loading pyannote speaker diarization pipeline...")
                self._diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
                )

                # Move to GPU if available
                try:
                    import torch

                    if torch.cuda.is_available():
                        self._diarization_pipeline.to(torch.device("cuda"))
                        logger.info("Diarization pipeline moved to GPU")
                except Exception as e:
                    logger.debug(f"Could not move diarization to GPU: {e}")

                logger.info("Pyannote diarization pipeline loaded")

            except ImportError:
                logger.warning("pyannote.audio not installed, diarization disabled")
                return None
            except Exception as e:
                logger.warning(f"Failed to load diarization pipeline: {e}")
                return None

        return self._diarization_pipeline

    async def submit_job(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> str:
        """Submit audio for local faster-whisper transcription."""
        job_id = str(uuid.uuid4())
        return job_id

    async def get_status(self, provider_job_id: str) -> TranscriptResult:
        """Local processing is synchronous, status always completed."""
        return TranscriptResult(
            provider_job_id=provider_job_id, status=TranscriptionStatus.COMPLETED
        )

    async def transcribe(
        self, audio_path: Path, speakers_expected: int = 2, language: str = "en"
    ) -> TranscriptResult:
        """Transcribe audio using faster-whisper."""
        job_id = str(uuid.uuid4())
        logger.info(f"Starting faster-whisper transcription for {audio_path}")

        try:
            # Run CPU/GPU-intensive transcription in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self._transcribe_sync(audio_path, language)
            )

            # Apply diarization if available and requested
            if speakers_expected > 1 and self.supports_diarization:
                diarization_result = await loop.run_in_executor(
                    None,
                    lambda: self._diarize_sync(audio_path, result, speakers_expected),
                )
                if diarization_result:
                    result = diarization_result

            logger.info(
                f"Faster-whisper transcription complete: "
                f"{len(result['utterances'])} utterances, "
                f"{result['duration_ms'] / 1000:.1f}s audio"
            )

            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.COMPLETED,
                utterances=result["utterances"],
                full_text=result["full_text"],
                duration_ms=result["duration_ms"],
                cost_cents=0,
                raw_response=result.get("raw"),
            )

        except Exception as e:
            logger.error(f"Faster-whisper transcription failed: {e}")
            return TranscriptResult(
                provider_job_id=job_id,
                status=TranscriptionStatus.FAILED,
                error_message=str(e),
            )

    def _transcribe_sync(self, audio_path: Path, language: str) -> dict:
        """Synchronous faster-whisper transcription."""
        model = self._load_model()

        # Transcribe with optimized settings
        segments, info = model.transcribe(
            str(audio_path),
            language=language if language else None,
            task="transcribe",
            vad_filter=True,  # Skip silence for speed
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
            word_timestamps=True,
            temperature=0.0,  # Deterministic output
            beam_size=5,
            best_of=5,
            condition_on_previous_text=True,
        )

        # Process segments
        utterances = []
        full_text_parts = []
        duration_ms = int(info.duration * 1000)

        for segment in segments:
            text = segment.text.strip()
            if text:
                utterances.append(
                    Utterance(
                        speaker="A",  # Single speaker without diarization
                        text=text,
                        start_ms=int(segment.start * 1000),
                        end_ms=int(segment.end * 1000),
                        confidence=(
                            segment.avg_logprob
                            if hasattr(segment, "avg_logprob")
                            else None
                        ),
                        words=(
                            [
                                {
                                    "word": w.word,
                                    "start": w.start,
                                    "end": w.end,
                                    "probability": w.probability,
                                }
                                for w in (segment.words or [])
                            ]
                            if segment.words
                            else None
                        ),
                    )
                )
                full_text_parts.append(text)

        return {
            "utterances": utterances,
            "full_text": " ".join(full_text_parts),
            "duration_ms": duration_ms,
            "raw": {
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
            },
        }

    def _diarize_sync(
        self, audio_path: Path, whisper_result: dict, num_speakers: int = 2
    ) -> Optional[dict]:
        """Apply speaker diarization to faster-whisper results."""
        pipeline = self._load_diarization()
        if pipeline is None:
            return None

        try:
            logger.info(
                f"Running speaker diarization (expecting {num_speakers} speakers)"
            )

            # Run diarization with speaker count hint
            diarization = pipeline(
                str(audio_path),
                num_speakers=num_speakers if num_speakers > 0 else None,
            )

            # Map whisper segments to speakers
            utterances = []
            speaker_map = {}
            speaker_count = 0

            for utt in whisper_result["utterances"]:
                seg_start = utt.start_ms / 1000
                seg_end = utt.end_ms / 1000
                seg_mid = (seg_start + seg_end) / 2

                # Find speaker at segment midpoint
                speaker_label = "A"
                for turn, _, spk in diarization.itertracks(yield_label=True):
                    if turn.start <= seg_mid <= turn.end:
                        # Map speaker IDs to A, B, C, etc.
                        if spk not in speaker_map:
                            speaker_map[spk] = chr(65 + speaker_count)
                            speaker_count += 1
                        speaker_label = speaker_map[spk]
                        break

                utterances.append(
                    Utterance(
                        speaker=speaker_label,
                        text=utt.text,
                        start_ms=utt.start_ms,
                        end_ms=utt.end_ms,
                        confidence=utt.confidence,
                        words=utt.words,
                    )
                )

            logger.info(f"Diarization complete: {len(speaker_map)} speakers detected")

            return {
                "utterances": utterances,
                "full_text": whisper_result["full_text"],
                "duration_ms": whisper_result["duration_ms"],
                "raw": {
                    **whisper_result.get("raw", {}),
                    "speakers_detected": len(speaker_map),
                    "speaker_map": speaker_map,
                },
            }

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return None

    def get_model_info(self) -> dict:
        """Get information about loaded model."""
        device, compute_type = self._detect_device_and_compute()
        return {
            "model": self._model_name,
            "device": device,
            "compute_type": compute_type,
            "loaded": self._model is not None,
            "diarization_available": self.supports_diarization,
        }
