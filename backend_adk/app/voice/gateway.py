"""Compatibility gateway for legacy session callers in the ADK backend."""
from fastapi import HTTPException

from app.core.config import Settings


class VoiceGateway:
    """Report that backend_adk serves voice through the call-center WebSocket."""
    def __init__(self, settings: Settings) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings

    async def create_realtime_session(self) -> dict:
        """Return a compatibility response for the non-native ADK cascaded voice paths."""
        if self.settings.voice_provider in {"cascaded_pipeline", "elevenlabs_pipeline"}:
            return {
                "architecture": self.settings.voice_provider,
                "message": "The ADK backend uses /api/v1/callcenter/realtime/ws for voice sessions.",
            }
        raise HTTPException(
            status_code=501,
            detail="OpenAI native realtime sessions are not implemented in backend_adk.",
        )
