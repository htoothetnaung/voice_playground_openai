"""Defines the common contract for providers that can create frontend-compatible realtime session payloads."""
from abc import ABC, abstractmethod
from typing import Any


class VoiceProvider(ABC):
    """Abstract provider contract for creating frontend-compatible realtime voice session payloads."""

    @abstractmethod
    async def create_realtime_session(self) -> dict[str, Any]:
        """Create a realtime session payload compatible with the frontend."""
