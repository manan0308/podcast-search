from fastapi import APIRouter

from app.services.transcription import get_available_providers, get_provider

router = APIRouter()


@router.get("")
async def list_providers():
    """
    List available transcription providers.

    Returns provider capabilities including:
    - name: Provider identifier
    - display_name: Human-readable name
    - max_concurrent: Maximum parallel transcription jobs
    - cost_per_hour_cents: Cost per hour of audio (0 for local)
    - supports_diarization: Whether speaker diarization is supported
    - available: Whether the provider is configured and ready to use
    - note: Additional information about the provider
    """
    providers = get_available_providers()
    return {"providers": providers}


@router.get("/{provider_name}")
async def get_provider_info(provider_name: str):
    """Get detailed information about a specific provider."""
    providers = get_available_providers()

    for p in providers:
        if p["name"] == provider_name:
            return p

    return {"error": f"Provider '{provider_name}' not found"}


@router.post("/{provider_name}/estimate")
async def estimate_cost(
    provider_name: str,
    duration_seconds: int,
):
    """
    Estimate transcription cost for a given duration.

    Args:
        provider_name: The provider to use
        duration_seconds: Total audio duration in seconds

    Returns:
        Estimated cost in cents
    """
    try:
        provider = get_provider(provider_name)
        cost_cents = provider.estimate_cost(duration_seconds)

        hours = duration_seconds / 3600

        return {
            "provider": provider_name,
            "duration_seconds": duration_seconds,
            "duration_hours": round(hours, 2),
            "cost_cents": cost_cents,
            "cost_dollars": round(cost_cents / 100, 2),
        }
    except ValueError as e:
        return {"error": str(e)}
