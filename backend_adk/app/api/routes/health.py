"""Returns service status, configured voice architecture options, timestamp, and uptime for frontend and deployment checks."""
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()
_STARTED_AT = monotonic()


@router.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    """Return operational status and configured voice architecture options for health checks."""
    return {
        "ok": True,
        "service": "atenxion-callcenter-adk-backend",
        "voice_provider": settings.voice_provider,
        "available_architectures": ["cascaded_pipeline", "elevenlabs_pipeline"],
        "llm_provider": "google_adk",
        "llm_model": settings.google_adk_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(monotonic() - _STARTED_AT, 3),
    }
