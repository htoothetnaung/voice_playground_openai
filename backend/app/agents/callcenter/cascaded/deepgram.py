"""Connects to Deepgram over WebSockets, converts provider messages into normalized transcript events, and handles keepalives."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass
class TranscriptEvent:
    """Normalized STT event passed from the Deepgram adapter into the cascaded runtime."""
    event_type: str
    text: str
    is_final: bool
    speech_final: bool
    raw: dict[str, Any] = field(default_factory=dict)


class DeepgramTranscriptAggregator:
    """Provider-specific parser that turns Deepgram messages into normalized transcript events."""
    def __init__(self, model: str) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.model = model
        self._final_segments: list[str] = []

    def ingest(self, message: dict[str, Any]) -> list[TranscriptEvent]:
        """Dispatch a raw Deepgram message to the parser for its model or event family."""
        message_type = message.get("type")
        if message_type == "TurnInfo":
            return self._ingest_flux(message)
        if message_type == "UtteranceEnd":
            return self._ingest_utterance_end(message)
        if message_type == "Results" or "channel" in message:
            return self._ingest_nova(message)
        return []

    def flush(self) -> TranscriptEvent | None:
        """Emit any buffered final transcript as a completed speech turn."""
        text = self._complete_text()
        if not text:
            return None
        self._final_segments.clear()
        return TranscriptEvent("stt_final", text, True, True, {})

    def _ingest_flux(self, message: dict[str, Any]) -> list[TranscriptEvent]:
        """Parse Deepgram Flux turn events into partial or final transcript events."""
        event = message.get("event")
        text = str(message.get("transcript") or "").strip()
        if not text:
            return []
        if event == "EndOfTurn":
            return [TranscriptEvent("stt_final", text, True, True, message)]
        if event in {"Update", "EagerEndOfTurn", "TurnResumed"}:
            return [TranscriptEvent("stt_partial", text, False, False, message)]
        return []

    def _ingest_nova(self, message: dict[str, Any]) -> list[TranscriptEvent]:
        """Parse Deepgram Nova results and accumulate final segments until speech is complete."""
        transcript = _extract_transcript(message).strip()
        if not transcript:
            return []

        is_final = bool(message.get("is_final"))
        speech_final = bool(message.get("speech_final"))
        if not is_final:
            return [TranscriptEvent("stt_partial", transcript, False, False, message)]

        self._final_segments.append(transcript)
        if speech_final:
            text = self._complete_text()
            self._final_segments.clear()
            return [TranscriptEvent("stt_final", text, True, True, message)]

        return [TranscriptEvent("stt_final", transcript, True, False, message)]

    def _ingest_utterance_end(self, message: dict[str, Any]) -> list[TranscriptEvent]:
        """Handle Nova utterance-end notifications by flushing buffered transcript text."""
        if message.get("last_word_end") == -1:
            return []
        flushed = self.flush()
        return [flushed] if flushed else []

    def _complete_text(self) -> str:
        """Join buffered final transcript segments into the text sent to the LLM stage."""
        return " ".join(segment for segment in self._final_segments if segment).strip()


class DeepgramStreamingTranscriber:
    """WebSocket adapter that streams microphone PCM to Deepgram and queues normalized transcript events."""
    def __init__(
        self,
        api_key: str,
        model: str,
        sample_rate: int,
        endpointing_ms: int,
        utterance_end_ms: int,
    ) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.endpointing_ms = endpointing_ms
        self.utterance_end_ms = utterance_end_ms
        self.aggregator = DeepgramTranscriptAggregator(model)
        self.events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self._socket: Any | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Open the Deepgram WebSocket and launch receive and keepalive tasks."""
        import websockets

        self._socket = await websockets.connect(
            self._url(),
            additional_headers={"Authorization": f"Token {self.api_key}"},
            ping_interval=20,
            ping_timeout=20,
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def send_audio(self, audio: bytes) -> None:
        """Forward raw PCM bytes from the browser to Deepgram."""
        if self._socket is not None:
            await self._socket.send(audio)

    async def flush_audio(self, duration_ms: int = 900) -> None:
        """Send a short block of silence to encourage Deepgram endpointing when the client commits audio."""
        bytes_per_ms = self.sample_rate * 2 / 1000
        await self.send_audio(bytes(round(bytes_per_ms * duration_ms)))

    async def close(self) -> None:
        """Cancel Deepgram background tasks and close the provider WebSocket."""
        for task in (self._receiver_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
        if self._socket is not None:
            try:
                await self._socket.send(json.dumps({"type": "CloseStream"}))
                await self._socket.close()
            except Exception:
                pass

    def _url(self) -> str:
        """Build the Deepgram streaming URL with model-specific query parameters."""
        is_flux = self.model.startswith("flux")
        endpoint = "v2/listen" if is_flux else "v1/listen"
        params: dict[str, Any] = {
            "model": self.model,
            "encoding": "linear16",
            "sample_rate": self.sample_rate,
        }
        if not is_flux:
            params.update(
                {
                    "channels": 1,
                    "smart_format": "true",
                    "interim_results": "true",
                    "endpointing": self.endpointing_ms,
                    "utterance_end_ms": self.utterance_end_ms,
                    "vad_events": "true",
                }
            )
        return f"wss://api.deepgram.com/{endpoint}?{urlencode(params)}"

    async def _receive_loop(self) -> None:
        """Receive Deepgram WebSocket messages and enqueue normalized transcript events."""
        assert self._socket is not None
        async for raw_message in self._socket:
            if isinstance(raw_message, bytes):
                continue
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            for event in self.aggregator.ingest(message):
                await self.events.put(event)

    async def _keepalive_loop(self) -> None:
        """Periodically send Deepgram keepalive messages while the stream is open."""
        while True:
            await asyncio.sleep(5)
            if self._socket is not None:
                await self._socket.send(json.dumps({"type": "KeepAlive"}))


def _extract_transcript(message: dict[str, Any]) -> str:
    """Extract the best transcript string from a Deepgram Nova result payload."""
    channel = message.get("channel") or {}
    alternatives = channel.get("alternatives") or []
    if not alternatives:
        return ""
    return str(alternatives[0].get("transcript") or "")
