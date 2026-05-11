"""Contains tests for deepgram adapter tests. in the backend."""
from app.agents.callcenter.cascaded.deepgram import (
    DeepgramStreamingTranscriber,
    DeepgramTranscriptAggregator,
)


def test_nova_aggregator_concatenates_final_segments_until_speech_final() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    aggregator = DeepgramTranscriptAggregator("nova-3")

    partial = aggregator.ingest(
        {
            "type": "Results",
            "is_final": False,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "my account"}]},
        }
    )
    assert len(partial) == 1
    assert partial[0].event_type == "stt_partial"

    first_final = aggregator.ingest(
        {
            "type": "Results",
            "is_final": True,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "my account number is"}]},
        }
    )
    assert first_final[0].text == "my account number is"
    assert first_final[0].speech_final is False

    speech_final = aggregator.ingest(
        {
            "type": "Results",
            "is_final": True,
            "speech_final": True,
            "channel": {"alternatives": [{"transcript": "two three four five"}]},
        }
    )
    assert speech_final[0].event_type == "stt_final"
    assert speech_final[0].speech_final is True
    assert speech_final[0].text == "my account number is two three four five"


def test_nova_utterance_end_flushes_buffer_without_duplicate_minus_one() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    aggregator = DeepgramTranscriptAggregator("nova-3")
    aggregator.ingest(
        {
            "type": "Results",
            "is_final": True,
            "speech_final": False,
            "channel": {"alternatives": [{"transcript": "I need billing help"}]},
        }
    )

    ignored = aggregator.ingest({"type": "UtteranceEnd", "last_word_end": -1})
    assert ignored == []

    flushed = aggregator.ingest({"type": "UtteranceEnd", "last_word_end": 1.2})
    assert len(flushed) == 1
    assert flushed[0].text == "I need billing help"
    assert flushed[0].speech_final is True


def test_flux_end_of_turn_emits_final_turn() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    aggregator = DeepgramTranscriptAggregator("flux-general-en")

    update = aggregator.ingest(
        {"type": "TurnInfo", "event": "Update", "transcript": "I need support"}
    )
    assert update[0].event_type == "stt_partial"

    end = aggregator.ingest(
        {
            "type": "TurnInfo",
            "event": "EndOfTurn",
            "transcript": "I need support with my internet.",
        }
    )
    assert len(end) == 1
    assert end[0].event_type == "stt_final"
    assert end[0].speech_final is True


def test_flux_url_uses_v2_without_channels_param() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    transcriber = DeepgramStreamingTranscriber(
        api_key="dg-key",
        model="flux-general-en",
        sample_rate=24000,
        endpointing_ms=300,
        utterance_end_ms=1000,
    )

    url = transcriber._url()

    assert url.startswith("wss://api.deepgram.com/v2/listen?")
    assert "model=flux-general-en" in url
    assert "encoding=linear16" in url
    assert "sample_rate=24000" in url
    assert "channels=" not in url


def test_nova_url_uses_v1_with_endpointing_params() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    transcriber = DeepgramStreamingTranscriber(
        api_key="dg-key",
        model="nova-3",
        sample_rate=24000,
        endpointing_ms=300,
        utterance_end_ms=1000,
    )

    url = transcriber._url()

    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "channels=1" in url
    assert "interim_results=true" in url
    assert "utterance_end_ms=1000" in url
