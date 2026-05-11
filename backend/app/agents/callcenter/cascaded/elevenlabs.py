"""Normalizes text for speech, streams PCM audio from ElevenLabs, and formats provider errors."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.agents.callcenter.cascaded.text_normalization import normalize_for_tts


class ElevenLabsTTSAdapter:
    """Streaming adapter that converts agent text into ElevenLabs PCM audio chunks."""
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str,
        sample_rate: int,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds

    async def synthesize_stream(self, text: str, voice_id: str | None = None) -> AsyncIterator[bytes]:
        """Normalize text, call ElevenLabs streaming TTS, and yield non-empty PCM byte chunks."""
        normalized_text = normalize_for_tts(text)
        selected_voice_id = voice_id or self.voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice_id}/stream"
        params = {"output_format": f"pcm_{self.sample_rate}"}
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": normalized_text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "use_speaker_boost": False,
                "speed": 1.08,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                url,
                params=params,
                headers=headers,
                json=payload,
            ) as response:
                if response.is_error:
                    body = await response.aread()
                    raise RuntimeError(_format_elevenlabs_error(response, body))
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk


def _format_elevenlabs_error(response: httpx.Response, body: bytes | None = None) -> str:
    """Convert ElevenLabs error responses into concise backend RuntimeError messages."""
    content = body if body is not None else response.content
    detail: Any
    try:
        parsed = json.loads(content.decode("utf-8", errors="replace"))
        detail = parsed.get("detail") if isinstance(parsed, dict) else parsed
    except Exception:
        detail = content.decode("utf-8", errors="replace")[:500]

    if isinstance(detail, dict):
        status = detail.get("status") or "unknown"
        message = detail.get("message") or response.reason_phrase
        return f"ElevenLabs TTS failed ({response.status_code}, {status}): {message}"
    return f"ElevenLabs TTS failed ({response.status_code}): {detail}"
