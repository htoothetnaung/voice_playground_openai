"""Calls OpenAI realtime session creation over HTTP and returns the session payload to the frontend."""
from typing import Any

import httpx

from app.core.config import Settings
from app.voice.base import VoiceProvider


class OpenAIRealtimeProvider(VoiceProvider):
    """Provider that creates native OpenAI realtime sessions through the OpenAI HTTP API."""
    def __init__(self, settings: Settings) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings

    async def create_realtime_session(self) -> dict[str, Any]:
        """Create or fetch the provider-specific realtime session payload consumed by the frontend."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.realtime_model,
                },
            )
            response.raise_for_status()
            return response.json()
