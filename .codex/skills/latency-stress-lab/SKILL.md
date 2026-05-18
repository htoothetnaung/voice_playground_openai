---
name: latency-stress-lab
description: Maintain and extend this repository's Latency Stress Lab for benchmarking call-center tool latency. Use when adding stress scenarios, interpreting stress-lab run results, configuring hosted OpenAI tool benchmarks, or debugging benchmark persistence/UI/API behavior in this repo.
---

# Latency Stress Lab

## Quick Start

Use this skill for the repo-local Stress Lab, not for the normal voice call path.

1. Inspect `backend/app/agents/callcenter/stress_lab.py` first.
2. Add or update scenarios in the scenario registry and keep each scenario output normalized.
3. Expose only benchmark behavior through `/api/v1/callcenter/stress-lab/*`.
4. Keep real hosted OpenAI tools behind `STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED=true`.
5. Run focused backend tests before touching frontend display logic.

## Scenario Rules

Choose `realistic_telecom` when the goal is to simulate internal systems such as CRM, billing, outage feeds, policy review, dispatch, or flaky dependencies. Use deterministic sleeps, deterministic failures, and realistic payload sizes so comparisons are repeatable.

Choose `hosted_openai_tool` when the goal is to measure an official OpenAI hosted tool such as `file_search`, `code_interpreter`, `web_search`, or `image_generation`. Hosted scenarios must declare required config and must skip cleanly when opt-in settings are absent.

Every scenario must define:

- stable `id`
- human `label`
- `kind` and `provider`
- `expected_output`
- timeout in milliseconds
- normalized `tool_calls`
- compact `output` metadata

Do not store large raw hosted-tool outputs in run results. Prefer item counts, item types, payload size, model, status, and timing.

## Latency Fields

Interpret results as benchmark telemetry:

- `latency_ms.total`: wall-clock time for one scenario iteration.
- `tool_calls[].duration_ms`: measured time inside a simulated or hosted tool call.
- `payload_size_bytes`: serialized result/output size estimate.
- `summary.p50_total_ms` and `summary.p95_total_ms`: suite-level latency comparison fields.
- `status`: `success`, `skipped`, `failed`, `timeout`, or aggregate partial statuses.

Skipped hosted scenarios are expected unless both the global lab flag and hosted-tool opt-in flag are enabled.

## Local Run Workflow

For mock-only development:

1. Set `STRESS_LAB_ENABLED=true`.
2. Leave `STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED=false`.
3. Run backend tests with `uv run --project backend pytest backend/tests/test_stress_lab.py`.
4. Start the app and use `/stress-lab` to run the enabled telecom scenarios.

For real hosted tool testing:

1. Set `STRESS_LAB_ENABLED=true`.
2. Set `STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED=true`.
3. Configure required values such as `STRESS_LAB_VECTOR_STORE_ID` for file search.
4. Run one hosted scenario at a time first, then increase repeat count or concurrency.

## Safety

Never add hosted OpenAI tool calls to the normal call-center agents as part of Stress Lab work. The Stress Lab must remain a separate benchmark surface so production call latency and behavior stay unchanged.
