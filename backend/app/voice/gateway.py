"""Chooses the configured voice provider and delegates session creation to the concrete implementation."""
from app.core.config import Settings
from app.voice.openai_provider import OpenAIRealtimeProvider


class VoiceGateway:
    """Small selector that keeps route code independent from the concrete voice provider implementation."""
    def __init__(self, settings: Settings) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings

    async def create_realtime_session(self) -> dict:
        """Create or fetch the provider-specific realtime session payload consumed by the frontend."""
        if self.settings.voice_provider != "openai_native":
            raise ValueError(
                f"Unsupported voice provider '{self.settings.voice_provider}'. "
                "Only 'openai_native' is implemented in the migration phase."
            )
        provider = OpenAIRealtimeProvider(self.settings)
        return await provider.create_realtime_session()
