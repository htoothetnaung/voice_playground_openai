"""Contains tests for cascaded runtime event tests. in the backend."""
import pytest

from app.agents.callcenter.cascaded import runtime as cascaded_runtime
from app.agents.callcenter.cascaded.runtime import (
    CallCenterCascadedRuntime,
    _direct_handoff_agent_name,
    _fixed_response_for_user_text,
    _handoff_intro,
    _handoff_outro,
    _should_skip_agent_sentence,
    _should_skip_handoff_sentence,
)
from app.agents.callcenter.context import CallCenterContext
from app.core.config import Settings


class FakeWebSocket:
    """Captures JSON payloads emitted by runtime helpers without opening a real WebSocket."""
    def __init__(self) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        """Support this module's backend workflow; see the file-level documentation for its role in the project."""
        self.messages.append(payload)


class FakeRawToolCall:
    """Test double for SDK raw tool-call item data."""
    name = "lookup_customer_profile"
    arguments = '{"phone_number":"+15551234567"}'


class FakeToolCallItem:
    """Test double for SDK tool call items emitted by streaming events."""
    raw_item = FakeRawToolCall()


class FakeToolOutputItem:
    """Test double for SDK tool output items emitted by streaming events."""
    raw_item = FakeRawToolCall()
    output = {"found": True}


class FakeRunItemEvent:
    """Test double that wraps fake SDK run item event names and payloads."""
    def __init__(self, name: str, item) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.name = name
        self.item = item


class FakeTTSAdapter:
    """Test TTS adapter that yields a fixed PCM chunk for runtime event assertions."""
    async def synthesize_stream(self, text: str, voice_id: str | None = None):
        """Normalize text, call ElevenLabs streaming TTS, and yield non-empty PCM byte chunks."""
        yield b"\x00\x00" * 960


@pytest.mark.asyncio
async def test_cascaded_runtime_normalizes_tool_events() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    runtime = CallCenterCascadedRuntime(Settings(OPENAI_API_KEY="sk-test"))
    websocket = FakeWebSocket()

    await runtime._send_run_item_event(
        websocket,
        FakeRunItemEvent("tool_called", FakeToolCallItem()),
        "callcenteragent",
    )
    await runtime._send_run_item_event(
        websocket,
        FakeRunItemEvent("tool_output", FakeToolOutputItem()),
        "callcenteragent",
    )

    assert websocket.messages[0]["type"] == "tool_start"
    assert websocket.messages[0]["tool_name"] == "lookup_customer_profile"
    assert websocket.messages[1]["type"] == "tool_end"
    assert websocket.messages[1]["output"] == {"found": True}


def test_cascaded_handoff_intro_uses_named_agents() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _handoff_intro("callcenteragent", "billingAgent")
        == "Hi, this is Austin with billing. Alice asked me to step in and help."
    )


def test_cascaded_handoff_outro_names_destination_team() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _handoff_outro("callcenteragent", "technicalSupportAgent")
        == "I'm sorry for the trouble. I'll transfer you to our technical support team so they can handle this."
    )


def test_cascaded_handoff_intro_for_supervisor_focuses_on_help_not_context() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    intro = _handoff_intro("technicalSupportAgent", "supervisorAgent")

    assert intro == "Hi, this is Sarah, the floor supervisor. Bob asked me to step in and help sort this out."
    assert "context" not in intro.lower()


def test_cascaded_handoff_outro_warns_before_returning_to_front_desk() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _handoff_outro("technicalSupportAgent", "callcenteragent")
        == "I'll bring Alice from our front desk back in now."
    )


def test_transfer_delay_is_fixed_phone_line_window() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert cascaded_runtime.HANDOFF_TRANSFER_DELAY_SECONDS == 2.5


def test_cascaded_runner_turn_limit_is_raised_above_sdk_default() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert cascaded_runtime.MAX_AGENT_TURNS == 30


def test_first_greeting_names_alice_front_desk() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    context = CallCenterContext(session_id="session", trace_id="trace")

    response = _fixed_response_for_user_text("hi", context, "callcenteragent")

    assert response == "Thanks for calling Atenxion, this is Alice at the front desk. How can I help today?"
    assert context.greeted is True


def test_human_escalation_returns_fixed_supervisor_number() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    context = CallCenterContext(session_id="session", trace_id="trace", greeted=True)

    response = _fixed_response_for_user_text("I want to talk to a human supervisor", context, "billingAgent")

    assert response is not None
    assert "09755083294" in response
    assert "Thank you very much for calling Atenxion" in response


def test_supervisor_request_is_not_human_escalation() -> None:
    """Verify plain supervisor requests stay inside the simulated AI supervisor flow."""
    context = CallCenterContext(session_id="session", trace_id="trace", greeted=True)

    assert _fixed_response_for_user_text("I want to talk to a supervisor", context, "billingAgent") is None
    assert (
        _direct_handoff_agent_name("I want to talk to a supervisor", "billingAgent", is_verified=True)
        == "supervisorAgent"
    )


def test_manager_request_routes_to_supervisor_agent() -> None:
    """Verify manager synonyms route to the AI supervisor agent."""
    assert (
        _direct_handoff_agent_name("Can I speak with a manager?", "callcenteragent", is_verified=True)
        == "supervisorAgent"
    )


def test_human_supervisor_request_still_returns_phone_number() -> None:
    """Verify explicit human supervisor wording exits the simulation."""
    context = CallCenterContext(session_id="session", trace_id="trace", greeted=True)

    response = _fixed_response_for_user_text("I need a human supervisor", context, "billingAgent")

    assert response is not None
    assert "09755083294" in response


def test_case_closed_confirmation_uses_final_closing_line() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    context = CallCenterContext(session_id="session", trace_id="trace", greeted=True)

    assert (
        _fixed_response_for_user_text("yes, the case is closed", context, "technicalSupportAgent")
        == "Thank you very much for calling Atenxion, and have a great rest of your day."
    )


def test_direct_handoff_routes_obvious_billing_question() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _direct_handoff_agent_name(
            "Why is my Bill so high this month?",
            "callcenteragent",
            is_verified=True,
        )
        == "billingAgent"
    )


def test_direct_handoff_requires_verified_context_for_account_questions() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _direct_handoff_agent_name(
            "Why is my Bill so high this month?",
            "callcenteragent",
            is_verified=False,
        )
        is None
    )


def test_direct_handoff_only_runs_from_triage_agent() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert _direct_handoff_agent_name("Why is my bill so high?", "billingAgent") is None


def test_direct_handoff_does_not_route_human_requests_to_simulated_agent() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert _direct_handoff_agent_name("I want a human representative", "callcenteragent") is None


def test_direct_handoff_routes_obvious_technical_question() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert (
        _direct_handoff_agent_name(
            "My internet keeps dropping.",
            "callcenteragent",
            is_verified=True,
        )
        == "technicalSupportAgent"
    )


def test_handoff_sentence_filter_removes_duplicate_transfer_narration() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert _should_skip_handoff_sentence(
        "(I have transferred you to our billing expert who will review your bill details with you.)",
        "billingAgent",
    )
    assert _should_skip_handoff_sentence(
        "I will connect you to our technical support specialist who can help diagnose and resolve this issue.",
        "technicalSupportAgent",
    )
    assert _should_skip_handoff_sentence(
        "I am a technical support specialist and will assist you with your internet issue.",
        "technicalSupportAgent",
    )
    assert _should_skip_handoff_sentence(
        "They have your account and service details ready. Thank you for your patience.",
        "technicalSupportAgent",
    )
    assert not _should_skip_handoff_sentence(
        "Could you please provide the zip code for your service address?",
        "technicalSupportAgent",
    )


def test_agent_sentence_filter_removes_same_team_transfer_claim() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    assert _should_skip_agent_sentence(
        "I'm now connecting you to our technical support team for further assistance with your internet issue.",
        "technicalSupportAgent",
        None,
    )
    assert not _should_skip_agent_sentence(
        "Could you please provide the zip code for your service address?",
        "technicalSupportAgent",
        None,
    )


@pytest.mark.asyncio
async def test_tts_worker_emits_transfer_and_agent_audio_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    monkeypatch.setattr(cascaded_runtime, "HANDOFF_TRANSFER_DELAY_SECONDS", 0)
    runtime = CallCenterCascadedRuntime(Settings(OPENAI_API_KEY="sk-test"))
    websocket = FakeWebSocket()
    metrics = runtime._new_metrics()
    queue = cascaded_runtime.asyncio.Queue()
    await queue.put(("Hello from billing.", True, "billingAgent"))
    await queue.put(None)

    await runtime._tts_worker(websocket, queue, "assistant-test", FakeTTSAdapter(), metrics)

    assert [message["type"] for message in websocket.messages] == [
        "transfer_audio_start",
        "transfer_audio_end",
        "agent_speech_start",
        "audio",
        "agent_speech_end",
    ]
    assert websocket.messages[0]["agent_name"] == "billingAgent"
    assert websocket.messages[0]["duration_ms"] == 0
    assert websocket.messages[2]["agent_name"] == "billingAgent"
    assert websocket.messages[3]["agent_name"] == "billingAgent"
