"""Streams PCM audio to ElevenLabs Scribe v2 realtime and normalizes transcript events."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

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
        commit_strategy: str = "vad",
        vad_silence_threshold_secs: float = 0.9,
        vad_threshold: float = 0.35,
        min_speech_duration_ms: int = 120,
        min_silence_duration_ms: int = 350,
        open_timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.commit_strategy = commit_strategy.lower().strip() or "vad"
        self.vad_silence_threshold_secs = vad_silence_threshold_secs
        self.vad_threshold = vad_threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.open_timeout_seconds = open_timeout_seconds
        self.events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self.aggregator = _EmptyTranscriptAggregator()
        self._connection: Any | None = None
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
        """Commit the current utterance for manual mode; VAD mode commits on server speech end."""
        if self.commit_strategy == "vad":
            return
        await self._send_audio_chunk(b"", commit=True)

    async def transcribe_pcm(self, audio: bytes) -> str:
        """Transcribe a push-to-talk PCM clip through a short-lived realtime session."""
        if not audio:
            return ""

        transcriber = ElevenLabsRealtimeTranscriber(
            api_key=self.api_key,
            model=self.model,
            sample_rate=self.sample_rate,
            commit_strategy="manual",
            open_timeout_seconds=self.open_timeout_seconds,
        )
        await transcriber.start()
        try:
            await transcriber._send_audio_chunk(audio, commit=False)
            await transcriber._send_audio_chunk(b"", commit=True)
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
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception:
                pass
        self._connection = None

    async def _open_socket(self) -> None:
        from elevenlabs.realtime import ScribeRealtime

        logger.info("Opening ElevenLabs Scribe realtime STT stream", extra={"model": self.model})
        client = ScribeRealtime(api_key=self.api_key)
        self._connection = await client.connect(self._connection_options())
        self._register_connection_handlers(self._connection)

    async def _send_audio_chunk(self, audio: bytes, *, commit: bool) -> None:
        async with self._send_lock:
            if self._connection is None:
                await self._restart_socket()
            try:
                if self._connection is not None:
                    if commit:
                        await self._connection.commit()
                    else:
                        await self._connection.send(
                            {"audio_base_64": base64.b64encode(audio).decode("ascii")}
                        )
                    return
            except _transient_connection_errors():
                await self._restart_socket()
                if self._connection is not None:
                    if commit:
                        await self._connection.commit()
                    else:
                        await self._connection.send(
                            {"audio_base_64": base64.b64encode(audio).decode("ascii")}
                        )

    async def _restart_socket(self) -> None:
        """Open a fresh realtime stream after the provider closes a completed session."""
        if self._closed:
            return
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception:
                pass
        self._connection = None
        await self._open_socket()

    def _connection_options(self) -> dict[str, Any]:
        from elevenlabs.realtime import CommitStrategy

        options: dict[str, Any] = {
            "model_id": self.model,
            "audio_format": _audio_format_for_sample_rate(self.sample_rate),
            "sample_rate": self.sample_rate,
            "commit_strategy": CommitStrategy.VAD
            if self.commit_strategy == "vad"
            else CommitStrategy.MANUAL,
        }
        if self.commit_strategy == "vad":
            options.update(
                {
                    "vad_silence_threshold_secs": self.vad_silence_threshold_secs,
                    "vad_threshold": self.vad_threshold,
                    "min_speech_duration_ms": self.min_speech_duration_ms,
                    "min_silence_duration_ms": self.min_silence_duration_ms,
                }
            )
        return options

    def _register_connection_handlers(self, connection: Any) -> None:
        from elevenlabs.realtime import RealtimeEvents

        def enqueue_transcript(message: dict[str, Any]) -> None:
            event = _normalize_scribe_event(message)
            if event is not None:
                self.events.put_nowait(event)

        def log_error(message: dict[str, Any]) -> None:
            logger.warning("ElevenLabs realtime STT error: %s", message.get("error") or message)

        def mark_closed(*_: Any) -> None:
            if not self._closed:
                self._connection = None

        connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, enqueue_transcript)
        connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, enqueue_transcript)
        connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT_WITH_TIMESTAMPS, enqueue_transcript)
        connection.on(RealtimeEvents.ERROR, log_error)
        connection.on(RealtimeEvents.CLOSE, mark_closed)


def _audio_format_for_sample_rate(sample_rate: int) -> Any:
    from elevenlabs.realtime import AudioFormat

    formats = {
        8000: AudioFormat.PCM_8000,
        16000: AudioFormat.PCM_16000,
        22050: AudioFormat.PCM_22050,
        24000: AudioFormat.PCM_24000,
        44100: AudioFormat.PCM_44100,
        48000: AudioFormat.PCM_48000,
    }
    try:
        return formats[sample_rate]
    except KeyError as exc:
        raise ValueError(f"Unsupported ElevenLabs realtime PCM sample rate: {sample_rate}") from exc


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
