"""Tests for the Google ADK call-center graph and route runner adapter."""
from types import SimpleNamespace

import pytest

from app.agents.callcenter.graph import build_callcenter_agent_map
from app.agents.callcenter import runner as runner_module
from app.agents.callcenter.runner import CallCenterAdkRunner
from app.core.config import Settings


def test_adk_graph_builds_expected_agent_names() -> None:
    agents = build_callcenter_agent_map(model="gemini-test")

    assert set(agents) == {
        "callcenteragent",
        "billingAgent",
        "technicalSupportAgent",
        "retentionAgent",
        "supervisorAgent",
        "humanEscalationAgent",
    }
    assert agents["callcenteragent"].sub_agents


def test_adk_graph_exposes_optional_helper_tools() -> None:
    agents = build_callcenter_agent_map(model="gemini-test")

    billing_tool_names = {tool.__name__ for tool in agents["billingAgent"].tools}
    supervisor_tool_names = {tool.__name__ for tool in agents["supervisorAgent"].tools}
    escalation_tool_names = {tool.__name__ for tool in agents["humanEscalationAgent"].tools}

    assert "atenxion_bank_tool" in billing_tool_names
    assert "atenxion_bank_tool" in supervisor_tool_names
    assert "search_gmail_customer_history" in escalation_tool_names


@pytest.mark.asyncio
async def test_adk_runner_returns_existing_route_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEngine:
        async def stream_turn(self, input_text, session_id, context):
            context.verified = True
            context.active_account_id = "ATX-204871"
            yield SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text="Hello from ADK")]),
                is_final_response=lambda: True,
            )

    monkeypatch.setattr(runner_module, "CallCenterAdkEngine", lambda settings: FakeEngine())
    runner = CallCenterAdkRunner(Settings(GOOGLE_API_KEY="test-google-key"))

    result = await runner.run_turn("hello", session_id="session-test")

    assert result["session_id"] == "session-test"
    assert result["final_output"] == "Hello from ADK"
    assert result["trace"]["verified"] is True
    assert result["trace"]["active_account_id"] == "ATX-204871"
