"""Tests for the Latency Stress Lab service."""

import pytest

from app.agents.callcenter.stress_lab import StressLabService, StressLabStore
from app.core.config import Settings


def _settings(tmp_path, **overrides) -> Settings:
    defaults = {
        "OPENAI_API_KEY": "sk-test",
        "STRESS_LAB_ENABLED": False,
        "STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED": False,
        "CALLCENTER_RAG_VECTOR_STORE_ID": "",
        "STRESS_LAB_RESULTS_PATH": str(tmp_path / "stress_runs.json"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_stress_lab_lists_disabled_scenarios_by_default(tmp_path) -> None:
    """Scenarios are visible but unavailable until the lab is enabled."""
    service = StressLabService(_settings(tmp_path))

    scenarios = service.list_scenarios()

    assert scenarios
    assert all(scenario["enabled"] is False for scenario in scenarios)
    assert any("STRESS_LAB_ENABLED" in scenario["skip_reason"] for scenario in scenarios)


def test_stress_lab_hosted_tools_skip_without_real_tool_opt_in(tmp_path) -> None:
    """Hosted tools remain disabled even when mock stress scenarios are enabled."""
    service = StressLabService(_settings(tmp_path, STRESS_LAB_ENABLED=True))

    scenarios = service.list_scenarios()
    hosted = [scenario for scenario in scenarios if scenario["kind"] == "hosted_openai_tool"]
    telecom = [scenario for scenario in scenarios if scenario["kind"] == "realistic_telecom"]

    assert hosted
    assert all(scenario["enabled"] is False for scenario in hosted)
    assert all(scenario["enabled"] is True for scenario in telecom)
    assert all("STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED" in scenario["skip_reason"] for scenario in hosted)
    assert any(scenario["id"] == "openai_vector_store_direct_search" for scenario in hosted)


@pytest.mark.asyncio
async def test_stress_lab_mock_suite_records_timings_and_tool_calls(tmp_path) -> None:
    """Mock telecom scenarios produce normalized latency and tool-call data."""
    settings = _settings(tmp_path, STRESS_LAB_ENABLED=True)
    service = StressLabService(settings, store=StressLabStore(settings, db=None))

    run = await service.run(
        scenario_ids=["telecom_slow_crm_lookup", "telecom_billing_dispute_package"],
        repeat_count=1,
        concurrency=2,
    )

    assert run["status"] == "success"
    assert run["summary"]["scenario_count"] == 2
    assert run["summary"]["success_count"] == 2
    assert run["summary"]["p95_total_ms"] > 0
    assert run["tool_calls"]
    assert all("duration_ms" in call for call in run["tool_calls"])


@pytest.mark.asyncio
async def test_stress_lab_json_fallback_persists_runs_without_mongo(tmp_path) -> None:
    """Runs can be fetched from the local JSON fallback store."""
    settings = _settings(tmp_path, STRESS_LAB_ENABLED=True)
    store = StressLabStore(settings, db=None)
    service = StressLabService(settings, store=store)

    run = await service.run(scenario_ids=["telecom_slow_crm_lookup"])
    fetched = await service.get_run(run["run_id"])

    assert fetched is not None
    assert fetched["run_id"] == run["run_id"]
    assert fetched["summary"]["iteration_count"] == 1


@pytest.mark.asyncio
async def test_stress_lab_run_marks_hosted_scenario_skipped_when_unconfigured(tmp_path) -> None:
    """A hosted scenario run does not call OpenAI unless all opt-in config is present."""
    settings = _settings(tmp_path, STRESS_LAB_ENABLED=True)
    service = StressLabService(settings, store=StressLabStore(settings, db=None))

    run = await service.run(scenario_ids=["openai_code_interpreter_billing_analysis"])

    assert run["status"] == "skipped"
    assert run["summary"]["skipped_count"] == 1
    assert "STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED" in run["results"][0]["skip_reason"]


@pytest.mark.asyncio
async def test_stress_lab_direct_vector_search_skips_without_vector_store_id(tmp_path) -> None:
    """Direct vector search requires the Atenxion RAG vector store id."""
    settings = _settings(
        tmp_path,
        STRESS_LAB_ENABLED=True,
        STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED=True,
    )
    service = StressLabService(settings, store=StressLabStore(settings, db=None))

    run = await service.run(scenario_ids=["openai_vector_store_direct_search"])

    assert run["status"] == "skipped"
    assert run["summary"]["skipped_count"] == 1
    assert "CALLCENTER_RAG_VECTOR_STORE_ID" in run["results"][0]["skip_reason"]
