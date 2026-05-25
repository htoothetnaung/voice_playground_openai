"""Contains tests for sentence buffering and tts tests. in the backend."""
import pytest
import httpx

from app.agents.callcenter.cascaded.elevenlabs import (
    ElevenLabsTTSAdapter,
    _format_elevenlabs_error,
)
from app.agents.callcenter.cascaded.sentence_buffer import SentenceBuffer
from app.agents.callcenter.cascaded.text_normalization import normalize_for_tts


def test_sentence_buffer_handles_callcenter_abbreviations_and_money() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    buffer = SentenceBuffer(min_length=10)
    chunks = [
        "I checked Dr. ",
        "Lee's notes. ",
        "Your credit is $20. ",
        "CASE-12345 remains open.",
    ]
    sentences: list[str] = []
    for chunk in chunks:
        sentences.extend(buffer.add(chunk))
    remaining = buffer.flush()
    if remaining:
        sentences.append(remaining)

    assert sentences == [
        "I checked Dr. Lee's notes.",
        "Your credit is $20.",
        "CASE-12345 remains open.",
    ]


def test_normalize_for_tts_expands_common_numeric_text() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    text = normalize_for_tts(
        "Your $20 credit posts on 2026-05-29. Call 555-123-4567 about case 12345."
    )

    assert "20 dollars" in text
    assert "May 29, 2026" in text
    assert "5 5 5 1 2 3 4 5 6 7" in text
    assert "1 2 3 4 5" in text


def test_normalize_for_tts_suppresses_long_backend_identifiers() -> None:
    """Long backend IDs should not be read aloud while phones and money still are."""
    text = normalize_for_tts(
        "I checked user ID 6a0d6b143cac1525e1e4ce87. "
        "Transaction id 507f1f77bcf86cd799439012 is complete. "
        "Call 09661200650 about $146.32, not reference 12345678901234567890."
    )

    assert "6a0d6b143cac1525e1e4ce87" not in text
    assert "507f1f77bcf86cd799439012" not in text
    assert "the user ID you provided" in text
    assert "the transaction ID" in text
    assert "0 9 6 6 1 2 0 0 6 5 0" in text
    assert "146 dollars and 32 cents" in text
    assert "12345678901234567890" not in text
    assert "the long ID" in text


@pytest.mark.asyncio
async def test_elevenlabs_adapter_streams_pcm_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    captured: dict[str, object] = {}

    class FakeResponse:
        """Groups the FakeResponse behavior or data used by this backend module."""
        is_error = False

        def raise_for_status(self) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

        async def aiter_bytes(self):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            yield b"abc"
            yield b""
            yield b"def"

    class FakeStream:
        """Groups the FakeStream behavior or data used by this backend module."""
        async def __aenter__(self) -> FakeResponse:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

    class FakeClient:
        """Groups the FakeClient behavior or data used by this backend module."""
        def __init__(self, timeout: float) -> None:
            """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
            captured["timeout"] = timeout

        async def __aenter__(self) -> "FakeClient":
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

        def stream(self, method: str, url: str, params, headers, json):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            captured["json"] = json
            return FakeStream()

    monkeypatch.setattr("app.agents.callcenter.cascaded.elevenlabs.httpx.AsyncClient", FakeClient)

    adapter = ElevenLabsTTSAdapter(
        api_key="eleven-key",
        voice_id="voice",
        model="eleven_flash_v2_5",
        sample_rate=24000,
    )

    chunks = [chunk async for chunk in adapter.synthesize_stream("Your $20 credit is ready.")]

    assert chunks == [b"abc", b"def"]
    assert captured["params"] == {"output_format": "pcm_24000"}
    assert captured["json"]["model_id"] == "eleven_flash_v2_5"
    assert "20 dollars" in captured["json"]["text"]


@pytest.mark.asyncio
async def test_elevenlabs_adapter_can_override_voice_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    captured: dict[str, object] = {}

    class FakeResponse:
        """Groups the FakeResponse behavior or data used by this backend module."""
        is_error = False

        async def aiter_bytes(self):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            yield b"pcm"

    class FakeStream:
        """Groups the FakeStream behavior or data used by this backend module."""
        async def __aenter__(self) -> FakeResponse:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

    class FakeClient:
        """Groups the FakeClient behavior or data used by this backend module."""
        def __init__(self, timeout: float) -> None:
            """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
            return None

        async def __aenter__(self) -> "FakeClient":
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

        def stream(self, method: str, url: str, params, headers, json):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            captured["url"] = url
            return FakeStream()

    monkeypatch.setattr("app.agents.callcenter.cascaded.elevenlabs.httpx.AsyncClient", FakeClient)

    adapter = ElevenLabsTTSAdapter(
        api_key="eleven-key",
        voice_id="default-voice",
        model="eleven_flash_v2_5",
        sample_rate=24000,
    )

    chunks = [chunk async for chunk in adapter.synthesize_stream("Hello.", voice_id="agent-voice")]

    assert chunks == [b"pcm"]
    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/agent-voice/stream"


@pytest.mark.asyncio
async def test_elevenlabs_adapter_retries_transient_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify transient DNS/connect failures retry before surfacing a TTS error."""
    attempts = 0

    async def no_sleep(_: float) -> None:
        return None

    class FakeResponse:
        """Successful retry response with one PCM chunk."""
        is_error = False

        async def aiter_bytes(self):
            """Yield a single chunk after the retry succeeds."""
            yield b"pcm"

    class FakeStream:
        """First stream enter fails, second stream enter succeeds."""
        async def __aenter__(self) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeClient:
        """Fake httpx client that exposes the stream context manager."""
        def __init__(self, timeout: float) -> None:
            return None

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, params, headers, json):
            return FakeStream()

    monkeypatch.setattr("app.agents.callcenter.cascaded.elevenlabs.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.agents.callcenter.cascaded.elevenlabs.asyncio.sleep", no_sleep)

    adapter = ElevenLabsTTSAdapter(
        api_key="eleven-key",
        voice_id="voice",
        model="eleven_flash_v2_5",
        sample_rate=24000,
    )

    chunks = [chunk async for chunk in adapter.synthesize_stream("Hello.")]

    assert attempts == 2
    assert chunks == [b"pcm"]


@pytest.mark.asyncio
async def test_elevenlabs_adapter_reads_stream_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    class FakeResponse:
        """Groups the FakeResponse behavior or data used by this backend module."""
        is_error = True

        status_code = 401
        reason_phrase = "Unauthorized"

        async def aread(self) -> bytes:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            self._content = (
                b'{"detail":{"status":"quota_exceeded","message":"API key quota exceeded."}}'
            )
            return self._content

        def json(self):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return httpx.Response(401, content=self._content).json()

        @property
        def text(self) -> str:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return self._content.decode("utf-8")

    class FakeStream:
        """Groups the FakeStream behavior or data used by this backend module."""
        async def __aenter__(self) -> FakeResponse:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

    class FakeClient:
        """Groups the FakeClient behavior or data used by this backend module."""
        def __init__(self, timeout: float) -> None:
            """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
            return None

        async def __aenter__(self) -> "FakeClient":
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return None

        def stream(self, method: str, url: str, params, headers, json):
            """Support this module's backend workflow; see the file-level documentation for its role in the project."""
            return FakeStream()

    monkeypatch.setattr("app.agents.callcenter.cascaded.elevenlabs.httpx.AsyncClient", FakeClient)

    adapter = ElevenLabsTTSAdapter(
        api_key="eleven-key",
        voice_id="voice",
        model="eleven_flash_v2_5",
        sample_rate=24000,
    )

    with pytest.raises(RuntimeError, match="quota_exceeded"):
        _ = [chunk async for chunk in adapter.synthesize_stream("Hello.")]


def test_format_elevenlabs_error_includes_provider_detail() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    response = httpx.Response(
        401,
        json={
            "detail": {
                "status": "quota_exceeded",
                "message": "This request exceeds your API key quota.",
            }
        },
    )

    assert (
        _format_elevenlabs_error(response)
        == "ElevenLabs TTS failed (401, quota_exceeded): This request exceeds your API key quota."
    )
