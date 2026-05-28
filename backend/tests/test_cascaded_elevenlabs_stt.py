"""Tests for the ElevenLabs Scribe realtime STT adapter."""

import base64

import pytest

from app.agents.callcenter.cascaded.elevenlabs_stt import (
    ElevenLabsRealtimeTranscriber,
    _audio_format_for_sample_rate,
    _normalize_scribe_event,
)


def test_elevenlabs_realtime_options_use_scribe_v2_vad_pcm_16k() -> None:
    """Verify the SDK connection options use Scribe realtime with provider VAD."""
    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=16000,
    )

    options = transcriber._connection_options()

    assert options["model_id"] == "scribe_v2_realtime"
    assert str(options["audio_format"]) == "AudioFormat.PCM_16000"
    assert options["sample_rate"] == 16000
    assert str(options["commit_strategy"]) == "CommitStrategy.VAD"
    assert options["vad_silence_threshold_secs"] == 0.9
    assert options["vad_threshold"] == 0.35
    assert options["min_speech_duration_ms"] == 120
    assert options["min_silence_duration_ms"] == 350


def test_elevenlabs_audio_format_rejects_unsupported_sample_rate() -> None:
    """Unsupported browser sample rates should fail before opening a provider socket."""
    with pytest.raises(ValueError, match="Unsupported ElevenLabs realtime PCM sample rate"):
        _audio_format_for_sample_rate(12345)


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
    """Verify audio is sent through the SDK connection as base64 PCM."""
    sent_messages: list[dict] = []
    commit_count = 0

    class FakeConnection:
        async def send(self, message: dict) -> None:
            sent_messages.append(message)

        async def commit(self) -> None:
            nonlocal commit_count
            commit_count += 1

    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=16000,
    )
    transcriber._connection = FakeConnection()

    await transcriber._send_audio_chunk(b"\x01\x02", commit=False)
    await transcriber._send_audio_chunk(b"", commit=True)

    assert sent_messages == [{"audio_base_64": base64.b64encode(b"\x01\x02").decode("ascii")}]
    assert commit_count == 1


@pytest.mark.asyncio
async def test_elevenlabs_send_audio_chunk_reopens_closed_stream() -> None:
    """Verify a clean provider close does not make the next user utterance fail."""
    sent_messages: list[dict] = []
    restart_count = 0

    class FakeConnection:
        async def send(self, message: dict) -> None:
            sent_messages.append(message)

        async def commit(self) -> None:
            pass

    transcriber = ElevenLabsRealtimeTranscriber(
        api_key="eleven-key",
        model="scribe_v2_realtime",
        sample_rate=16000,
    )

    async def fake_restart_socket() -> None:
        nonlocal restart_count
        restart_count += 1
        transcriber._connection = FakeConnection()

    transcriber._connection = None
    transcriber._restart_socket = fake_restart_socket  # type: ignore[method-assign]

    await transcriber._send_audio_chunk(b"\x03\x04", commit=False)

    assert restart_count == 1
    assert sent_messages[0]["audio_base_64"] == base64.b64encode(b"\x03\x04").decode("ascii")
