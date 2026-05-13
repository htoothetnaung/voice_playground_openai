"""Connects to Deepgram over WebSockets, converts provider messages into normalized transcript events, and handles keepalives."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


logger = logging.getLogger(__name__)


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
        open_timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.endpointing_ms = endpointing_ms
        self.utterance_end_ms = utterance_end_ms
        self.open_timeout_seconds = open_timeout_seconds
        self.aggregator = DeepgramTranscriptAggregator(model)
        self.events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self._socket: Any | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False
        self._next_reconnect_at = 0.0

    async def start(self) -> None:
        """Open the Deepgram WebSocket and launch receive and keepalive tasks."""
        self._closed = False
        await self._open_socket()

    async def _open_socket(self) -> None:
        """Open a Deepgram WebSocket and start background receive/keepalive tasks."""
        import websockets

        logger.info("Opening Deepgram STT stream", extra={"model": self.model})
        self._socket = await websockets.connect(
            self._url(),
            additional_headers={"Authorization": f"Token {self.api_key}"},
            ping_interval=20,
            ping_timeout=20,
            open_timeout=self.open_timeout_seconds,
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def send_audio(self, audio: bytes) -> None:
        """Forward raw PCM bytes from the browser to Deepgram."""
        if self._closed:
            return

        async with self._send_lock:
            if self._socket is None:
                if not self._can_attempt_reconnect():
                    return
                try:
                    await self._restart_socket()
                except _transient_connection_errors():
                    self._mark_reconnect_backoff()
                    return

            try:
                if self._socket is not None:
                    await self._socket.send(audio)
            except _transient_connection_errors():
                if not self._can_attempt_reconnect():
                    return
                try:
                    await self._restart_socket()
                except _transient_connection_errors():
                    self._mark_reconnect_backoff()
                    return
                try:
                    if self._socket is not None:
                        await self._socket.send(audio)
                except _transient_connection_errors():
                    self._socket = None
                    self._mark_reconnect_backoff()

    async def flush_audio(self, duration_ms: int = 900) -> None:
        """Send a short block of silence to encourage Deepgram endpointing when the client commits audio."""
        bytes_per_ms = self.sample_rate * 2 / 1000
        await self.send_audio(bytes(round(bytes_per_ms * duration_ms)))

    async def transcribe_pcm(self, audio: bytes) -> str:
        """Transcribe a complete PCM16 clip through Deepgram's pre-recorded endpoint."""
        import httpx

        if not audio:
            return ""

        params = {
            "model": self.model,
            "smart_format": "true",
        }
        wav_audio = _pcm16_wav(audio, self.sample_rate)
        async with httpx.AsyncClient(timeout=self.open_timeout_seconds) as client:
            response = await client.post(
                f"https://api.deepgram.com/v1/listen?{urlencode(params)}",
                content=wav_audio,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "audio/wav",
                },
            )
            response.raise_for_status()

        payload = response.json()
        channel = payload.get("results", {}).get("channels", [{}])[0]
        alternatives = channel.get("alternatives") or []
        if not alternatives:
            return ""
        return str(alternatives[0].get("transcript") or "").strip()

    async def close(self) -> None:
        """Cancel Deepgram background tasks and close the provider WebSocket."""
        self._closed = True
        for task in (self._receiver_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
        if self._socket is not None:
            try:
                await self._socket.send(json.dumps({"type": "CloseStream"}))
                await self._socket.close()
            except Exception:
                pass
        self._socket = None

    async def _restart_socket(self) -> None:
        """Reconnect after Deepgram closes the stream without taking down the app WebSocket."""
        if self._closed:
            return

        logger.info("Restarting Deepgram STT stream", extra={"model": self.model})
        for task in (self._receiver_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()

        if self._socket is not None:
            try:
                await self._socket.close()
            except Exception:
                pass

        self._socket = None
        self.aggregator = DeepgramTranscriptAggregator(self.model)
        await self._open_socket()

    def _can_attempt_reconnect(self) -> bool:
        """Throttle reconnect attempts while the client keeps streaming microphone frames."""
        loop = asyncio.get_running_loop()
        return loop.time() >= self._next_reconnect_at

    def _mark_reconnect_backoff(self) -> None:
        """Avoid retrying a failed opening handshake for every incoming audio frame."""
        loop = asyncio.get_running_loop()
        self._next_reconnect_at = loop.time() + 3
        self._socket = None

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
        try:
            async for raw_message in self._socket:
                if isinstance(raw_message, bytes):
                    continue
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                for event in self.aggregator.ingest(message):
                    await self.events.put(event)
        except _transient_connection_errors():
            if not self._closed:
                self._socket = None

    async def _keepalive_loop(self) -> None:
        """Periodically send Deepgram keepalive messages while the stream is open."""
        while True:
            await asyncio.sleep(5)
            try:
                if self._socket is not None:
                    await self._socket.send(json.dumps({"type": "KeepAlive"}))
            except _transient_connection_errors():
                if not self._closed:
                    self._socket = None
                return


def _extract_transcript(message: dict[str, Any]) -> str:
    """Extract the best transcript string from a Deepgram Nova result payload."""
    channel = message.get("channel") or {}
    alternatives = channel.get("alternatives") or []
    if not alternatives:
        return ""
    return str(alternatives[0].get("transcript") or "")


def _pcm16_wav(audio: bytes, sample_rate: int) -> bytes:
    """Wrap little-endian mono PCM16 bytes in a minimal WAV container."""
    channels = 1
    bits_per_sample = 16
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    data_size = len(audio)
    riff_size = 36 + data_size

    return b"".join(
        [
            b"RIFF",
            riff_size.to_bytes(4, "little"),
            b"WAVE",
            b"fmt ",
            (16).to_bytes(4, "little"),
            (1).to_bytes(2, "little"),
            channels.to_bytes(2, "little"),
            sample_rate.to_bytes(4, "little"),
            byte_rate.to_bytes(4, "little"),
            block_align.to_bytes(2, "little"),
            bits_per_sample.to_bytes(2, "little"),
            b"data",
            data_size.to_bytes(4, "little"),
            audio,
        ]
    )


def _transient_connection_errors() -> tuple[type[BaseException], ...]:
    """Return transient Deepgram WebSocket errors that should not tear down the app session."""
    import websockets

    return (
        TimeoutError,
        OSError,
        websockets.exceptions.ConnectionClosed,
        websockets.exceptions.InvalidHandshake,
    )
