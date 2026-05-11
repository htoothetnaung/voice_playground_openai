"""Creates short-lived session payloads for frontend clients that connect to OpenAI native realtime audio."""
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.voice.gateway import VoiceGateway

router = APIRouter()


@router.get("/api/session")
async def create_session(settings: Settings = Depends(get_settings)) -> dict:
    """Support this module's backend workflow; see the file-level documentation for its role in the project."""
    gateway = VoiceGateway(settings)
    return await gateway.create_realtime_session()
