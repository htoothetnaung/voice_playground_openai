"""Latency Stress Lab scenarios, execution, summaries, and persistence."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any
from uuid import uuid4

from openai import AsyncOpenAI

from app.agents.callcenter.tools import _search_atenxion_vector_store
from app.agents.callcenter.cascaded.events import serialize
from app.core.config import Settings
from app.core.mongo import get_mongo_database

ScenarioHandler = Callable[["StressScenarioContext"], Awaitable[dict[str, Any]]]
_UNSET = object()


@dataclass(frozen=True)
class StressScenario:
    """Scenario metadata and executable handler."""

    id: str
    label: str
    kind: str
    provider: str
    expected_output: str
    timeout_ms: int
    handler: ScenarioHandler
    requires_real_openai_tools: bool = False
    required_config: tuple[str, ...] = ()


@dataclass
class StressScenarioContext:
    """Runtime context for one scenario iteration."""

    settings: Settings
    client: AsyncOpenAI | None
    iteration: int


class StressLabStore:
    """Persist stress-lab runs to MongoDB with JSON fallback for local development."""

    def __init__(self, settings: Settings, db: Any = _UNSET) -> None:
        self.settings = settings
        self.db = db if db is not _UNSET else get_mongo_database(settings)
        self.path = Path(settings.stress_lab_results_path)

    async def save_run(self, run: dict[str, Any]) -> None:
        """Store one completed run."""
        payload = serialize(run)
        if self.db is not None:
            try:
                await self.db.stress_lab_runs.update_one(
                    {"run_id": payload["run_id"]},
                    {"$set": payload},
                    upsert=True,
                )
                return
            except Exception:
                pass
        await self._save_json(payload)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch one run by identifier."""
        if self.db is not None:
            try:
                record = await self.db.stress_lab_runs.find_one({"run_id": run_id})
                if record:
                    return serialize({key: value for key, value in record.items() if key != "_id"})
            except Exception:
                pass
        runs = await self._load_json()
        return runs.get(run_id)

    async def _save_json(self, run: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        runs = await self._load_json()
        runs[run["run_id"]] = run
        self.path.write_text(json.dumps(runs, indent=2, sort_keys=True), encoding="utf-8")

    async def _load_json(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}


class StressLabService:
    """Run latency stress scenarios and produce normalized benchmark results."""

    def __init__(
        self,
        settings: Settings,
        *,
        store: StressLabStore | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or StressLabStore(settings)
        self.client = client
        self.scenarios = _scenario_registry()

    def list_scenarios(self) -> list[dict[str, Any]]:
        """Return scenario metadata with enablement and skip reasons."""
        return [self._scenario_metadata(scenario) for scenario in self.scenarios.values()]

    async def run(
        self,
        *,
        scenario_ids: list[str] | None = None,
        repeat_count: int = 1,
        concurrency: int = 1,
    ) -> dict[str, Any]:
        """Run selected scenarios and persist a normalized result."""
        repeat_count = max(1, min(repeat_count, 20))
        concurrency = max(1, min(concurrency, 5))
        selected_ids = scenario_ids or list(self.scenarios)
        selected = [self.scenarios[scenario_id] for scenario_id in selected_ids if scenario_id in self.scenarios]
        if not selected:
            raise ValueError("No known stress-lab scenarios were selected.")

        run_id = f"stress-{uuid4().hex}"
        started_at = _utc_iso()
        semaphore = asyncio.Semaphore(concurrency)
        tasks = []
        for scenario in selected:
            for iteration in range(1, repeat_count + 1):
                tasks.append(self._run_one_with_semaphore(semaphore, scenario, iteration))

        results = await asyncio.gather(*tasks)
        completed_at = _utc_iso()
        run = {
            "run_id": run_id,
            "scenario_id": "suite" if len(selected) > 1 else selected[0].id,
            "scenario_ids": [scenario.id for scenario in selected],
            "started_at": started_at,
            "completed_at": completed_at,
            "status": _aggregate_status(results),
            "latency_ms": _aggregate_latency(results),
            "tool_calls": [call for result in results for call in result.get("tool_calls", [])],
            "summary": _summary(results),
            "results": results,
        }
        await self.store.save_run(run)
        return run

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Read a persisted run."""
        return await self.store.get_run(run_id)

    async def _run_one_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        scenario: StressScenario,
        iteration: int,
    ) -> dict[str, Any]:
        async with semaphore:
            return await self._run_one(scenario, iteration)

    async def _run_one(self, scenario: StressScenario, iteration: int) -> dict[str, Any]:
        metadata = self._scenario_metadata(scenario)
        started_at = _utc_iso()
        start = monotonic()
        if not metadata["enabled"]:
            completed_at = _utc_iso()
            return {
                "scenario_id": scenario.id,
                "iteration": iteration,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": "skipped",
                "skip_reason": metadata["skip_reason"],
                "latency_ms": {"total": 0},
                "tool_calls": [],
                "output": {},
            }

        client = self.client
        if client is None and scenario.requires_real_openai_tools:
            client = AsyncOpenAI(api_key=self.settings.openai_api_key)

        try:
            payload = await asyncio.wait_for(
                scenario.handler(
                    StressScenarioContext(
                        settings=self.settings,
                        client=client,
                        iteration=iteration,
                    )
                ),
                timeout=scenario.timeout_ms / 1000,
            )
            status = "success"
            error = None
        except TimeoutError:
            payload = {"tool_calls": [], "output": {}}
            status = "timeout"
            error = f"Scenario exceeded {scenario.timeout_ms}ms timeout."
        except Exception as exc:
            payload = {"tool_calls": [], "output": {}}
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"

        completed_at = _utc_iso()
        total_ms = _elapsed_ms(start)
        latency = {"total": total_ms}
        latency.update(payload.get("latency_ms", {}))
        result = {
            "scenario_id": scenario.id,
            "iteration": iteration,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "latency_ms": latency,
            "tool_calls": payload.get("tool_calls", []),
            "output": payload.get("output", {}),
        }
        if error:
            result["error"] = error
        return result

    def _scenario_metadata(self, scenario: StressScenario) -> dict[str, Any]:
        skip_reason = _skip_reason(self.settings, scenario)
        return {
            "id": scenario.id,
            "label": scenario.label,
            "kind": scenario.kind,
            "provider": scenario.provider,
            "expected_output": scenario.expected_output,
            "timeout_ms": scenario.timeout_ms,
            "required_config": list(scenario.required_config),
            "requires_real_openai_tools": scenario.requires_real_openai_tools,
            "enabled": skip_reason is None,
            "skip_reason": skip_reason,
        }


def _scenario_registry() -> dict[str, StressScenario]:
    scenarios = [
        StressScenario(
            id="telecom_slow_crm_lookup",
            label="Slow CRM Lookup",
            kind="realistic_telecom",
            provider="simulated_internal",
            expected_output="Customer profile, entitlement summary, and one delayed CRM tool call.",
            timeout_ms=2500,
            handler=_slow_crm_lookup,
        ),
        StressScenario(
            id="telecom_billing_dispute_package",
            label="Billing Dispute Package",
            kind="realistic_telecom",
            provider="simulated_internal",
            expected_output="Sequential billing, usage, credit-policy, and dispute package calls.",
            timeout_ms=3500,
            handler=_billing_dispute_package,
        ),
        StressScenario(
            id="telecom_outage_parallel_investigation",
            label="Parallel Outage Investigation",
            kind="realistic_telecom",
            provider="simulated_internal",
            expected_output="Parallel outage checks with one deterministic flaky dependency.",
            timeout_ms=3000,
            handler=_outage_parallel_investigation,
        ),
        StressScenario(
            id="telecom_policy_escalation_digest",
            label="Policy Escalation Digest",
            kind="realistic_telecom",
            provider="simulated_internal",
            expected_output="Large policy payload scan and structured escalation recommendation.",
            timeout_ms=3000,
            handler=_policy_escalation_digest,
        ),
        StressScenario(
            id="openai_file_search_policy_query",
            label="OpenAI File Search Policy Query",
            kind="hosted_openai_tool",
            provider="openai",
            expected_output="Responses API file_search call over the configured vector store.",
            timeout_ms=30000,
            handler=_openai_file_search,
            requires_real_openai_tools=True,
            required_config=("STRESS_LAB_VECTOR_STORE_ID",),
        ),
        StressScenario(
            id="openai_vector_store_direct_search",
            label="OpenAI Vector Store Direct Search",
            kind="hosted_openai_tool",
            provider="openai",
            expected_output="Direct vector store search over the Atenxion RAG corpus.",
            timeout_ms=30000,
            handler=_openai_vector_store_direct_search,
            requires_real_openai_tools=True,
            required_config=("CALLCENTER_RAG_VECTOR_STORE_ID",),
        ),
        StressScenario(
            id="openai_code_interpreter_billing_analysis",
            label="OpenAI Code Interpreter Billing Analysis",
            kind="hosted_openai_tool",
            provider="openai",
            expected_output="Responses API code_interpreter call for a small billing anomaly analysis.",
            timeout_ms=45000,
            handler=_openai_code_interpreter,
            requires_real_openai_tools=True,
        ),
        StressScenario(
            id="openai_web_search_support_lookup",
            label="OpenAI Web Search Support Lookup",
            kind="hosted_openai_tool",
            provider="openai",
            expected_output="Responses API web_search result with sourced public information.",
            timeout_ms=30000,
            handler=_openai_web_search,
            requires_real_openai_tools=True,
        ),
        StressScenario(
            id="openai_image_generation_support_artifact",
            label="OpenAI Image Generation Support Artifact",
            kind="hosted_openai_tool",
            provider="openai",
            expected_output="Responses API image_generation call for a support-call visual artifact.",
            timeout_ms=60000,
            handler=_openai_image_generation,
            requires_real_openai_tools=True,
        ),
    ]
    return {scenario.id: scenario for scenario in scenarios}


async def _slow_crm_lookup(_ctx: StressScenarioContext) -> dict[str, Any]:
    async with _timed_tool("crm_profile_lookup", "simulated_internal") as call:
        await asyncio.sleep(0.35)
        output = {"account_id": "ATX-204871", "entitlements": 3, "risk": "medium"}
        call["payload_size_bytes"] = _payload_size(output)
    return {"tool_calls": [call], "output": output}


async def _billing_dispute_package(_ctx: StressScenarioContext) -> dict[str, Any]:
    calls = []
    for name, delay in (
        ("latest_bill_fetch", 0.16),
        ("usage_charge_audit", 0.24),
        ("credit_policy_lookup", 0.13),
        ("dispute_package_build", 0.18),
    ):
        async with _timed_tool(name, "simulated_internal") as call:
            await asyncio.sleep(delay)
            call["payload_size_bytes"] = 320 + len(name)
        calls.append(call)
    return {
        "tool_calls": calls,
        "output": {
            "bill_id": "BILL-2026-04",
            "drivers": ["international_calls", "roaming_day_passes"],
            "recommended_credit_usd": 20,
        },
    }


async def _outage_parallel_investigation(ctx: StressScenarioContext) -> dict[str, Any]:
    async def provider_call(name: str, delay: float, flaky: bool = False) -> dict[str, Any]:
        async with _timed_tool(name, "simulated_internal") as call:
            await asyncio.sleep(delay)
            if flaky and ctx.iteration % 2 == 0:
                call["status"] = "failed"
                call["error"] = "Synthetic provider timeout after partial response."
            call["payload_size_bytes"] = 256
        return call

    calls = await asyncio.gather(
        provider_call("area_outage_feed", 0.22),
        provider_call("line_diagnostics", 0.31),
        provider_call("dispatch_capacity", 0.27, flaky=True),
    )
    return {
        "tool_calls": calls,
        "output": {
            "outage_detected": False,
            "flaky_dependency_failed": any(call["status"] == "failed" for call in calls),
            "recommendation": "continue_device_troubleshooting",
        },
    }


async def _policy_escalation_digest(_ctx: StressScenarioContext) -> dict[str, Any]:
    policy_blob = "\n".join(
        f"POL-{index:03d}: Retention and billing exception rule {index}."
        for index in range(1, 160)
    )
    calls = []
    async with _timed_tool("policy_document_scan", "simulated_internal") as call:
        await asyncio.sleep(0.22)
        call["payload_size_bytes"] = len(policy_blob.encode("utf-8"))
    calls.append(call)
    async with _timed_tool("structured_escalation_decision", "simulated_internal") as call:
        await asyncio.sleep(0.19)
        call["payload_size_bytes"] = 540
    calls.append(call)
    return {
        "tool_calls": calls,
        "output": {
            "matched_policy_count": 159,
            "decision": "supervisor_review_recommended",
            "confidence": 0.82,
        },
    }


async def _openai_file_search(ctx: StressScenarioContext) -> dict[str, Any]:
    assert ctx.client is not None
    tool = {
        "type": "file_search",
        "vector_store_ids": [ctx.settings.stress_lab_vector_store_id],
        "max_num_results": 3,
    }
    return await _responses_tool_call(
        ctx,
        tool_name="file_search",
        tools=[tool],
        input_text="Find the most relevant Atenxion support policy for a disputed roaming charge.",
    )


async def _openai_vector_store_direct_search(ctx: StressScenarioContext) -> dict[str, Any]:
    assert ctx.client is not None
    async with _timed_tool("vector_store_search", "openai") as call:
        output = await _search_atenxion_vector_store(
            ctx.client,
            ctx.settings.callcenter_rag_vector_store_id or "",
            query="Find supervisor policy for roaming charge goodwill exceptions.",
            max_num_results=5,
            topic="goodwill_credit",
            service_type="billing",
        )
        results = output.get("results", [])
        call["payload_size_bytes"] = _payload_size(results)
        call["metadata"] = {
            "vector_store_id": ctx.settings.callcenter_rag_vector_store_id,
            "result_count": len(results),
            "has_more": bool(output.get("has_more", False)),
            "search_latency_ms": output.get("latency_ms", 0),
        }
    return {
        "tool_calls": [call],
        "output": call["metadata"],
    }


async def _openai_code_interpreter(ctx: StressScenarioContext) -> dict[str, Any]:
    assert ctx.client is not None
    return await _responses_tool_call(
        ctx,
        tool_name="code_interpreter",
        tools=[{"type": "code_interpreter", "container": {"type": "auto"}}],
        input_text=(
            "Use the python tool to calculate mean, max, and anomaly count for these monthly "
            "bills: [98, 101, 97, 146, 99, 103]. Return concise JSON-like findings."
        ),
    )


async def _openai_web_search(ctx: StressScenarioContext) -> dict[str, Any]:
    return await _responses_tool_call(
        ctx,
        tool_name="web_search",
        tools=[{"type": "web_search"}],
        input_text="Search for public telecom outage support best practices and answer in one sentence with citations.",
    )


async def _openai_image_generation(ctx: StressScenarioContext) -> dict[str, Any]:
    return await _responses_tool_call(
        ctx,
        tool_name="image_generation",
        tools=[{"type": "image_generation", "size": "1024x1024", "quality": "low"}],
        input_text="Generate a simple clean support-call dashboard illustration for a latency benchmark report.",
    )


async def _responses_tool_call(
    ctx: StressScenarioContext,
    *,
    tool_name: str,
    tools: list[dict[str, Any]],
    input_text: str,
) -> dict[str, Any]:
    assert ctx.client is not None
    async with _timed_tool(tool_name, "openai") as call:
        response = await ctx.client.responses.create(
            model=ctx.settings.stress_lab_openai_model,
            tools=tools,
            tool_choice="required",
            input=input_text,
        )
        dumped = response.model_dump() if hasattr(response, "model_dump") else response
        output_items = dumped.get("output", []) if isinstance(dumped, dict) else []
        call["payload_size_bytes"] = _payload_size(output_items)
        call["metadata"] = {
            "model": ctx.settings.stress_lab_openai_model,
            "output_item_types": [
                item.get("type") for item in output_items if isinstance(item, dict)
            ],
        }
    return {
        "tool_calls": [call],
        "output": {
            "output_item_count": len(output_items),
            "output_item_types": call["metadata"]["output_item_types"],
        },
    }


class _timed_tool:
    """Async context manager for normalized tool-call timing."""

    def __init__(self, name: str, provider: str) -> None:
        self.call = {
            "name": name,
            "type": name,
            "provider": provider,
            "status": "success",
            "duration_ms": 0,
            "payload_size_bytes": 0,
        }
        self._start = 0.0

    async def __aenter__(self) -> dict[str, Any]:
        self._start = monotonic()
        return self.call

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, _tb: Any) -> bool:
        self.call["duration_ms"] = _elapsed_ms(self._start)
        if exc is not None:
            self.call["status"] = "failed"
            self.call["error"] = f"{type(exc).__name__}: {exc}"
        return False


def _skip_reason(settings: Settings, scenario: StressScenario) -> str | None:
    if not settings.stress_lab_enabled:
        return "Set STRESS_LAB_ENABLED=true to run benchmark scenarios."
    if scenario.requires_real_openai_tools and not settings.stress_lab_real_openai_tools_enabled:
        return "Set STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED=true to run hosted OpenAI tool scenarios."
    missing = [
        name
        for name in scenario.required_config
        if not getattr(settings, _setting_attr(name), None)
    ]
    if missing:
        return f"Missing required config: {', '.join(missing)}."
    return None


def _setting_attr(env_name: str) -> str:
    return env_name.lower()


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed_ms(start: float) -> float:
    return round((monotonic() - start) * 1000, 3)


def _payload_size(value: Any) -> int:
    return len(json.dumps(serialize(value), sort_keys=True).encode("utf-8"))


def _aggregate_status(results: list[dict[str, Any]]) -> str:
    statuses = {result["status"] for result in results}
    if statuses == {"success"}:
        return "success"
    if statuses == {"skipped"}:
        return "skipped"
    if "failed" in statuses or "timeout" in statuses:
        return "partial_failure" if "success" in statuses else "failed"
    return "partial"


def _aggregate_latency(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [
        float(result.get("latency_ms", {}).get("total", 0))
        for result in results
        if result.get("status") != "skipped"
    ]
    if not totals:
        return {"total": 0, "p50": 0, "p95": 0}
    return {
        "total": round(sum(totals), 3),
        "p50": _percentile(totals, 50),
        "p95": _percentile(totals, 95),
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [
        float(result.get("latency_ms", {}).get("total", 0))
        for result in results
        if result.get("status") != "skipped"
    ]
    return {
        "scenario_count": len({result["scenario_id"] for result in results}),
        "iteration_count": len(results),
        "success_count": sum(1 for result in results if result["status"] == "success"),
        "failure_count": sum(1 for result in results if result["status"] in {"failed", "timeout"}),
        "skipped_count": sum(1 for result in results if result["status"] == "skipped"),
        "p50_total_ms": _percentile(totals, 50) if totals else 0,
        "p95_total_ms": _percentile(totals, 95) if totals else 0,
        "median_total_ms": round(median(totals), 3) if totals else 0,
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)
