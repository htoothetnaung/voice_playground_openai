"""Preserves the legacy session route while the ADK backend serves cascaded voice over WebSocket."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get("/api/session")
async def create_session(settings: Settings = Depends(get_settings)) -> dict:
    """Return a clear compatibility response because OpenAI native realtime is out of scope here."""
    if settings.voice_provider in {"cascaded_pipeline", "elevenlabs_pipeline"}:
        return {
            "architecture": settings.voice_provider,
            "message": "The ADK backend uses /api/v1/callcenter/realtime/ws for cascaded voice sessions.",
        }
    raise HTTPException(
        status_code=501,
        detail="OpenAI native realtime sessions are not implemented in backend_adk.",
    )
