"""Tests for the ElevenLabs Scribe realtime STT adapter."""

import base64
import json

import pytest

from app.agents.callcenter.cascaded.elevenlabs_stt import (
    ElevenLabsRealtimeTranscriber,
    _normalize_scribe_event,
)


def test_elevenlabs_realtime_url_uses_scribe_v2_manual_pcm() -> None:
    """Verify the realtime STT URL matches the documented Scribe websocket contract."""
    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=24000,
    )

    url = transcriber._url()

    assert url.startswith("wss://api.elevenlabs.io/v1/speech-to-text/realtime?")
    assert "model_id=scribe_v2_realtime" in url
    assert "audio_format=pcm_24000" in url
    assert "commit_strategy=manual" in url


def test_elevenlabs_normalizes_partial_and_committed_transcripts() -> None:
    """Verify Scribe realtime messages become the shared transcript event shape."""
    partial = _normalize_scribe_event(
        {"message_type": "partial_transcript", "text": "why is my"}
    )
    committed = _normalize_scribe_event(
        {"message_type": "committed_transcript", "text": "why is my bill high"}
    )

    assert partial is not None
    assert partial.event_type == "stt_partial"
    assert partial.text == "why is my"
    assert partial.speech_final is False
    assert committed is not None
    assert committed.event_type == "stt_final"
    assert committed.text == "why is my bill high"
    assert committed.speech_final is True


@pytest.mark.asyncio
async def test_elevenlabs_send_audio_chunk_uses_documented_payload() -> None:
    """Verify audio is sent as base64 input_audio_chunk JSON."""
    sent_messages: list[str] = []

    class FakeSocket:
        async def send(self, message: str) -> None:
            sent_messages.append(message)

    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=24000,
    )
    transcriber._socket = FakeSocket()

    await transcriber._send_audio_chunk(b"\x01\x02", commit=True)

    payload = json.loads(sent_messages[0])
    assert payload == {
        "message_type": "input_audio_chunk",
        "audio_base_64": base64.b64encode(b"\x01\x02").decode("ascii"),
        "commit": True,
        "sample_rate": 24000,
    }


@pytest.mark.asyncio
async def test_elevenlabs_send_audio_chunk_reopens_closed_stream() -> None:
    """Verify a clean provider close does not make the next user utterance fail."""
    sent_messages: list[str] = []
    restart_count = 0

    class FakeSocket:
        async def send(self, message: str) -> None:
            sent_messages.append(message)

    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=24000,
    )

    async def fake_restart_socket() -> None:
        nonlocal restart_count
        restart_count += 1
        transcriber._socket = FakeSocket()

    transcriber._socket = None
    transcriber._restart_socket = fake_restart_socket  # type: ignore[method-assign]

    await transcriber._send_audio_chunk(b"\x03\x04", commit=False)

    assert restart_count == 1
    payload = json.loads(sent_messages[0])
    assert payload["message_type"] == "input_audio_chunk"
    assert payload["audio_base_64"] == base64.b64encode(b"\x03\x04").decode("ascii")
    assert payload["commit"] is False
