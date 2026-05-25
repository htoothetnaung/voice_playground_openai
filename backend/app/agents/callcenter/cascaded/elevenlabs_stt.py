"""Streams PCM audio to ElevenLabs Scribe v2 realtime and normalizes transcript events."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import urlencode

from app.agents.callcenter.cascaded.deepgram import TranscriptEvent

logger = logging.getLogger(__name__)


class _EmptyTranscriptAggregator:
    """Compatibility shim for runtimes that may ask a transcriber to flush buffered text."""

    def flush(self) -> None:
        return None


class ElevenLabsRealtimeTranscriber:
    """WebSocket adapter for ElevenLabs Scribe v2 realtime transcription."""

    def __init__(
        self,
        api_key: str,
        model: str,
        sample_rate: int,
        open_timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.open_timeout_seconds = open_timeout_seconds
        self.events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self.aggregator = _EmptyTranscriptAggregator()
        self._socket: Any | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def start(self) -> None:
        """Open the ElevenLabs realtime STT WebSocket and start receiving events."""
        self._closed = False
        await self._open_socket()

    async def send_audio(self, audio: bytes) -> None:
        """Forward raw PCM bytes to ElevenLabs as one realtime audio chunk."""
        if self._closed or not audio:
            return
        await self._send_audio_chunk(audio, commit=False)

    async def flush_audio(self, duration_ms: int = 250) -> None:
        """Commit the current utterance by sending a short silence chunk with commit=true."""
        bytes_per_ms = self.sample_rate * 2 / 1000
        await self._send_audio_chunk(bytes(round(bytes_per_ms * duration_ms)), commit=True)

    async def transcribe_pcm(self, audio: bytes) -> str:
        """Transcribe a push-to-talk PCM clip through a short-lived realtime session."""
        if not audio:
            return ""

        transcriber = ElevenLabsRealtimeTranscriber(
            api_key=self.api_key,
            model=self.model,
            sample_rate=self.sample_rate,
            open_timeout_seconds=self.open_timeout_seconds,
        )
        await transcriber.start()
        try:
            await transcriber._send_audio_chunk(audio, commit=True)
            while True:
                event = await asyncio.wait_for(
                    transcriber.events.get(),
                    timeout=self.open_timeout_seconds,
                )
                if event.event_type == "stt_final":
                    return event.text
        finally:
            await transcriber.close()

    async def close(self) -> None:
        """Cancel background receive work and close the provider socket."""
        self._closed = True
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
        if self._socket is not None:
            try:
                await self._socket.close()
            except Exception:
                pass
        self._socket = None

    async def _open_socket(self) -> None:
        import websockets

        logger.info("Opening ElevenLabs Scribe realtime STT stream", extra={"model": self.model})
        self._socket = await websockets.connect(
            self._url(),
            additional_headers={"xi-api-key": self.api_key},
            ping_interval=20,
            ping_timeout=20,
            open_timeout=self.open_timeout_seconds,
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _send_audio_chunk(self, audio: bytes, *, commit: bool) -> None:
        payload = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(audio).decode("ascii"),
            "commit": commit,
            "sample_rate": self.sample_rate,
        }
        async with self._send_lock:
            if self._socket is None:
                await self._restart_socket()
            try:
                if self._socket is not None:
                    await self._socket.send(json.dumps(payload))
                    return
            except _transient_connection_errors():
                await self._restart_socket()
                if self._socket is not None:
                    await self._socket.send(json.dumps(payload))

    async def _restart_socket(self) -> None:
        """Open a fresh realtime stream after the provider closes a completed session."""
        if self._closed:
            return
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
        if self._socket is not None:
            try:
                await self._socket.close()
            except Exception:
                pass
        self._socket = None
        await self._open_socket()

    def _url(self) -> str:
        params = {
            "model_id": self.model,
            "audio_format": f"pcm_{self.sample_rate}",
            "commit_strategy": "manual",
            "no_verbatim": "true",
            "enable_logging": "true",
        }
        return f"wss://api.elevenlabs.io/v1/speech-to-text/realtime?{urlencode(params)}"

    async def _receive_loop(self) -> None:
        assert self._socket is not None
        try:
            async for raw_message in self._socket:
                if isinstance(raw_message, bytes):
                    continue
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                event = _normalize_scribe_event(message)
                if event is not None:
                    await self.events.put(event)
        except _transient_connection_errors():
            if not self._closed:
                self._socket = None
        finally:
            if not self._closed:
                self._socket = None


def _normalize_scribe_event(message: dict[str, Any]) -> TranscriptEvent | None:
    """Convert ElevenLabs realtime messages into the shared STT event shape."""
    message_type = str(message.get("message_type") or "")
    text = str(message.get("text") or "").strip()
    if message_type == "partial_transcript" and text:
        return TranscriptEvent("stt_partial", text, False, False, message)
    if message_type in {"committed_transcript", "committed_transcript_with_timestamps"} and text:
        return TranscriptEvent("stt_final", text, True, True, message)
    if message_type in {
        "error",
        "auth_error",
        "quota_exceeded",
        "commit_throttled",
        "unaccepted_terms",
        "rate_limited",
        "queue_overflow",
        "resource_exhausted",
        "session_time_limit_exceeded",
        "input_error",
        "chunk_size_exceeded",
        "insufficient_audio_activity",
        "transcriber_error",
    }:
        logger.warning("ElevenLabs realtime STT error: %s", message.get("error") or message_type)
    return None


def _transient_connection_errors() -> tuple[type[BaseException], ...]:
    import websockets

    return (
        TimeoutError,
        OSError,
        websockets.exceptions.ConnectionClosed,
        websockets.exceptions.InvalidHandshake,
    )
