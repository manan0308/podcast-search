from app.services.transcription.base import TranscriptionProvider
from app.services.transcription.assemblyai import AssemblyAIProvider
from app.services.transcription.deepgram import DeepgramProvider
from app.services.transcription.whisper import WhisperProvider
from app.services.transcription.faster_whisper import FasterWhisperProvider
from app.services.transcription.modal_cloud import ModalCloudProvider, MODAL_AVAILABLE
from app.services.transcription.modal_hybrid import ModalHybridProvider
from app.config import settings


def get_provider(provider_name: str | None = None) -> TranscriptionProvider:
    """
    Factory to get transcription provider instance.

    Args:
        provider_name: One of 'assemblyai', 'deepgram', 'whisper', 'faster-whisper', 'modal-cloud'.
                      If None, uses DEFAULT_TRANSCRIPTION_PROVIDER from settings.

    Returns:
        TranscriptionProvider instance

    Raises:
        ValueError: If provider is not configured or unknown
    """
    name = provider_name or settings.DEFAULT_TRANSCRIPTION_PROVIDER

    match name:
        case "assemblyai":
            if not settings.ASSEMBLYAI_API_KEY:
                raise ValueError("ASSEMBLYAI_API_KEY not configured")
            return AssemblyAIProvider(
                api_key=settings.ASSEMBLYAI_API_KEY,
                max_concurrent=settings.ASSEMBLYAI_MAX_CONCURRENT,
            )

        case "deepgram":
            if not settings.DEEPGRAM_API_KEY:
                raise ValueError("DEEPGRAM_API_KEY not configured")
            return DeepgramProvider(
                api_key=settings.DEEPGRAM_API_KEY,
                max_concurrent=settings.DEEPGRAM_MAX_CONCURRENT,
            )

        case "whisper":
            return WhisperProvider(
                model=settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                max_concurrent=settings.WHISPER_MAX_CONCURRENT,
            )

        case "faster-whisper":
            return FasterWhisperProvider(
                model=settings.FASTER_WHISPER_MODEL,
                device=settings.FASTER_WHISPER_DEVICE,
                compute_type=settings.FASTER_WHISPER_COMPUTE_TYPE,
                max_concurrent=settings.FASTER_WHISPER_MAX_CONCURRENT,
            )

        case "modal-cloud":
            if not MODAL_AVAILABLE:
                raise ValueError("Modal not installed. Run: pip install modal")
            return ModalCloudProvider(
                model=settings.MODAL_WHISPER_MODEL,
                gpu_type=settings.MODAL_GPU_TYPE,
                max_concurrent=settings.MODAL_MAX_CONCURRENT,
            )

        case "modal-hybrid":
            if not MODAL_AVAILABLE:
                raise ValueError("Modal not installed. Run: pip install modal")
            return ModalHybridProvider(
                model=settings.MODAL_WHISPER_MODEL,
                gpu_type=settings.MODAL_GPU_TYPE,
                max_concurrent=settings.MODAL_MAX_CONCURRENT,
            )

        case _:
            raise ValueError(f"Unknown transcription provider: {name}")


def get_available_providers() -> list[dict]:
    """
    Return list of available/configured providers with their capabilities.

    Returns:
        List of provider info dicts with:
        - name: Provider identifier
        - display_name: Human-readable name
        - max_concurrent: Max parallel jobs
        - cost_per_hour_cents: Cost per hour of audio
        - supports_diarization: Whether speaker diarization is supported
        - available: Whether the provider is configured and ready
        - note: Optional additional info
    """
    providers = []

    # AssemblyAI
    providers.append(
        {
            "name": "assemblyai",
            "display_name": "AssemblyAI",
            "max_concurrent": settings.ASSEMBLYAI_MAX_CONCURRENT,
            "cost_per_hour_cents": 37,
            "supports_diarization": True,
            "available": bool(settings.ASSEMBLYAI_API_KEY),
            "note": None,
        }
    )

    # Deepgram
    providers.append(
        {
            "name": "deepgram",
            "display_name": "Deepgram",
            "max_concurrent": settings.DEEPGRAM_MAX_CONCURRENT,
            "cost_per_hour_cents": 26,
            "supports_diarization": True,
            "available": bool(settings.DEEPGRAM_API_KEY),
            "note": None,
        }
    )

    # Whisper (original OpenAI whisper)
    whisper_available = True
    whisper_note = None

    try:
        import importlib.util
        if importlib.util.find_spec("whisper") is None:
            raise ImportError()
    except ImportError:
        whisper_available = False
        whisper_note = "openai-whisper not installed"

    providers.append(
        {
            "name": "whisper",
            "display_name": "Local Whisper (OpenAI)",
            "max_concurrent": settings.WHISPER_MAX_CONCURRENT,
            "cost_per_hour_cents": 0,
            "supports_diarization": False,
            "available": whisper_available,
            "note": (
                f"Original OpenAI Whisper on {settings.WHISPER_DEVICE.upper()}"
                if whisper_available
                else whisper_note
            ),
        }
    )

    # Faster-Whisper (4x faster than OpenAI Whisper)
    faster_whisper_available = True
    faster_whisper_note = None
    diarization_available = False

    try:
        if importlib.util.find_spec("faster_whisper") is None:
            raise ImportError()
    except ImportError:
        faster_whisper_available = False
        faster_whisper_note = "faster-whisper not installed"

    try:
        if importlib.util.find_spec("pyannote.audio") is not None:
            diarization_available = True
    except ImportError:
        pass

    device_info = settings.FASTER_WHISPER_DEVICE.upper()
    if device_info == "AUTO":
        try:
            import torch

            device_info = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
        except ImportError:
            device_info = "CPU"

    providers.append(
        {
            "name": "faster-whisper",
            "display_name": "Faster-Whisper (Local)",
            "max_concurrent": settings.FASTER_WHISPER_MAX_CONCURRENT,
            "cost_per_hour_cents": 0,
            "supports_diarization": diarization_available,
            "available": faster_whisper_available,
            "note": (
                f"4x faster on {device_info}, FREE"
                + (" + diarization" if diarization_available else "")
                if faster_whisper_available
                else faster_whisper_note
            ),
        }
    )

    # Modal Cloud (serverless GPU)
    import os

    modal_configured = bool(os.environ.get("MODAL_TOKEN_ID"))

    providers.append(
        {
            "name": "modal-cloud",
            "display_name": "Modal Cloud GPU",
            "max_concurrent": settings.MODAL_MAX_CONCURRENT,
            "cost_per_hour_cents": 3,  # ~$0.03/hr of audio
            "supports_diarization": False,
            "available": MODAL_AVAILABLE and modal_configured,
            "note": (
                f"70-200x realtime on {settings.MODAL_GPU_TYPE}, ~$0.03/hr"
                if MODAL_AVAILABLE
                else "modal not installed"
            ),
        }
    )

    # Modal Hybrid (local download + cloud transcription)
    providers.append(
        {
            "name": "modal-hybrid",
            "display_name": "Modal Hybrid (Recommended for bulk)",
            "max_concurrent": settings.MODAL_MAX_CONCURRENT,
            "cost_per_hour_cents": 3,
            "supports_diarization": False,
            "available": MODAL_AVAILABLE and modal_configured,
            "note": (
                "Downloads locally, transcribes on cloud GPU. Best for bulk channel imports."
                if MODAL_AVAILABLE
                else "modal not installed"
            ),
        }
    )

    return providers


def get_default_provider_name() -> str:
    """Get the name of the default transcription provider."""
    return settings.DEFAULT_TRANSCRIPTION_PROVIDER
