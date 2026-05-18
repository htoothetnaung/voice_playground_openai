"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityLogIcon,
  ArrowRightIcon,
  CheckCircledIcon,
  CrossCircledIcon,
  DashboardIcon,
  LightningBoltIcon,
  ReloadIcon,
} from "@radix-ui/react-icons";

type StressScenario = {
  id: string;
  label: string;
  kind: string;
  provider: string;
  expected_output: string;
  timeout_ms: number;
  required_config: string[];
  requires_real_openai_tools: boolean;
  enabled: boolean;
  skip_reason?: string | null;
};

type ScenarioResponse = {
  enabled: boolean;
  real_openai_tools_enabled: boolean;
  scenarios: StressScenario[];
};

type ToolCall = {
  name: string;
  provider: string;
  status: string;
  duration_ms: number;
  payload_size_bytes?: number;
  error?: string;
};

type StressResult = {
  scenario_id: string;
  iteration: number;
  status: string;
  skip_reason?: string;
  error?: string;
  latency_ms: Record<string, number>;
  tool_calls: ToolCall[];
};

type StressRun = {
  run_id: string;
  scenario_id: string;
  scenario_ids: string[];
  started_at: string;
  completed_at: string;
  status: string;
  latency_ms: Record<string, number>;
  tool_calls: ToolCall[];
  summary: {
    scenario_count: number;
    iteration_count: number;
    success_count: number;
    failure_count: number;
    skipped_count: number;
    p50_total_ms: number;
    p95_total_ms: number;
    median_total_ms: number;
  };
  results: StressResult[];
};

const kindLabels: Record<string, string> = {
  realistic_telecom: "Telecom simulation",
  hosted_openai_tool: "Hosted OpenAI tool",
};

function formatMs(value?: number) {
  if (typeof value !== "number") return "0 ms";
  return `${Math.round(value)} ms`;
}

function statusTone(status: string) {
  if (status === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "skipped") return "border-slate-200 bg-slate-100 text-slate-600";
  if (status === "partial_failure" || status === "partial") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-rose-200 bg-rose-50 text-rose-700";
}

export default function StressLabPage() {
  const [scenarioResponse, setScenarioResponse] = useState<ScenarioResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [kindFilter, setKindFilter] = useState("all");
  const [repeatCount, setRepeatCount] = useState(1);
  const [concurrency, setConcurrency] = useState(1);
  const [run, setRun] = useState<StressRun | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadScenarios() {
      try {
        const response = await fetch("/api/stress-lab/scenarios", { cache: "no-store" });
        if (!response.ok) throw new Error(`Scenario API returned ${response.status}`);
        const payload = (await response.json()) as ScenarioResponse;
        if (cancelled) return;
        setScenarioResponse(payload);
        setSelectedIds(payload.scenarios.filter((scenario) => scenario.enabled).map((scenario) => scenario.id));
        setError(null);
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load scenarios");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadScenarios();
    return () => {
      cancelled = true;
    };
  }, []);

  const scenarios = scenarioResponse?.scenarios ?? [];
  const filteredScenarios = useMemo(
    () =>
      scenarios.filter((scenario) => kindFilter === "all" || scenario.kind === kindFilter),
    [kindFilter, scenarios],
  );
  const selectedEnabledCount = scenarios.filter(
    (scenario) => selectedIds.includes(scenario.id) && scenario.enabled,
  ).length;

  function toggleScenario(scenario: StressScenario) {
    if (!scenario.enabled) return;
    setSelectedIds((current) =>
      current.includes(scenario.id)
        ? current.filter((id) => id !== scenario.id)
        : [...current, scenario.id],
    );
  }

  async function runSuite() {
    setIsRunning(true);
    setError(null);
    setRun(null);
    try {
      const response = await fetch("/api/stress-lab/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_ids: selectedIds,
          repeat_count: repeatCount,
          concurrency,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? payload.error ?? `Run API returned ${response.status}`);
      }
      setRun((await response.json()) as StressRun);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to run stress suite");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        <aside className="flex flex-col justify-between bg-slate-950 px-6 py-6 text-white">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-300 text-slate-950">
                <LightningBoltIcon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold">Latency Stress Lab</p>
                <p className="text-xs text-slate-400">Tool pressure testing</p>
              </div>
            </div>

            <div className="mt-10 space-y-3 text-sm text-slate-300">
              <div className="flex items-center gap-3 rounded-lg bg-white/10 px-3 py-2">
                <DashboardIcon className="h-4 w-4 text-cyan-300" />
                Benchmark suites
              </div>
              <div className="flex items-center gap-3 rounded-lg px-3 py-2">
                <ActivityLogIcon className="h-4 w-4 text-cyan-300" />
                Stage timing
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Link href="/admin" className="flex items-center justify-between rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200">
              Admin Console
              <ArrowRightIcon />
            </Link>
            <Link href="/" className="flex items-center justify-between rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200">
              Call Center Lab
              <ArrowRightIcon />
            </Link>
          </div>
        </aside>

        <section className="min-w-0">
          <header className="border-b border-slate-200 bg-white px-6 py-6 lg:px-8">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">Atenxion runtime lab</p>
                <h1 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950">
                  Latency Stress Lab
                </h1>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-medium">
                <span className={`rounded-full border px-3 py-1 ${scenarioResponse?.enabled ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-600"}`}>
                  STRESS_LAB_ENABLED: {scenarioResponse?.enabled ? "true" : "false"}
                </span>
                <span className={`rounded-full border px-3 py-1 ${scenarioResponse?.real_openai_tools_enabled ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-600"}`}>
                  Real OpenAI tools: {scenarioResponse?.real_openai_tools_enabled ? "on" : "off"}
                </span>
              </div>
            </div>
          </header>

          <div className="grid gap-4 p-4 lg:grid-cols-[minmax(320px,420px)_1fr] lg:p-6">
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">Scenarios</h2>
                  <p className="text-sm text-slate-500">{selectedEnabledCount} enabled selected</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedIds(scenarios.filter((scenario) => scenario.enabled).map((scenario) => scenario.id))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
                >
                  Select enabled
                </button>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
                {["all", "realistic_telecom", "hosted_openai_tool"].map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => setKindFilter(kind)}
                    className={`rounded-md border px-2 py-2 font-medium ${kindFilter === kind ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`}
                  >
                    {kind === "all" ? "All" : kind === "realistic_telecom" ? "Telecom" : "OpenAI"}
                  </button>
                ))}
              </div>

              <div className="mt-4 space-y-3">
                {isLoading && <p className="text-sm text-slate-500">Loading scenarios...</p>}
                {filteredScenarios.map((scenario) => (
                  <button
                    key={scenario.id}
                    type="button"
                    onClick={() => toggleScenario(scenario)}
                    className={`w-full rounded-lg border p-3 text-left transition ${selectedIds.includes(scenario.id) ? "border-cyan-400 bg-cyan-50" : "border-slate-200 bg-white"} ${!scenario.enabled ? "opacity-60" : ""}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{scenario.label}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {kindLabels[scenario.kind] ?? scenario.kind} · {scenario.provider} · {formatMs(scenario.timeout_ms)}
                        </p>
                      </div>
                      {scenario.enabled ? (
                        <CheckCircledIcon className="mt-0.5 h-4 w-4 text-emerald-600" />
                      ) : (
                        <CrossCircledIcon className="mt-0.5 h-4 w-4 text-slate-400" />
                      )}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-600">{scenario.expected_output}</p>
                    {!scenario.enabled && (
                      <p className="mt-2 text-xs font-medium text-amber-700">{scenario.skip_reason}</p>
                    )}
                  </button>
                ))}
              </div>
            </section>

            <section className="space-y-4">
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                  <label className="text-sm font-medium text-slate-700">
                    Repeat count
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={repeatCount}
                      onChange={(event) => setRepeatCount(Number(event.target.value))}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                    />
                  </label>
                  <label className="text-sm font-medium text-slate-700">
                    Concurrency
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={concurrency}
                      onChange={(event) => setConcurrency(Number(event.target.value))}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={runSuite}
                    disabled={isRunning || selectedIds.length === 0}
                    className="self-end rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    {isRunning ? (
                      <span className="flex items-center gap-2"><ReloadIcon className="h-4 w-4 animate-spin" /> Running</span>
                    ) : (
                      "Run suite"
                    )}
                  </button>
                </div>
                {error && <p className="mt-3 text-sm font-medium text-rose-700">{error}</p>}
              </div>

              <div className="grid gap-3 md:grid-cols-4">
                {[
                  ["Status", run?.status ?? "not run"],
                  ["Iterations", run?.summary.iteration_count ?? 0],
                  ["p50", formatMs(run?.summary.p50_total_ms)],
                  ["p95", formatMs(run?.summary.p95_total_ms)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
                    <p className="mt-2 text-xl font-semibold text-slate-950">{value}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 px-4 py-3">
                  <h2 className="text-base font-semibold">Run Results</h2>
                  {run && <p className="mt-1 text-xs text-slate-500">Run ID: {run.run_id}</p>}
                </div>
                <div className="divide-y divide-slate-100">
                  {!run && (
                    <p className="p-4 text-sm text-slate-500">
                      Run a suite to inspect per-scenario latency, tool calls, payload sizes, and failures.
                    </p>
                  )}
                  {run?.results.map((result) => (
                    <div key={`${result.scenario_id}-${result.iteration}`} className="p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-950">{result.scenario_id}</p>
                          <p className="text-xs text-slate-500">Iteration {result.iteration} · total {formatMs(result.latency_ms.total)}</p>
                        </div>
                        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(result.status)}`}>
                          {result.status}
                        </span>
                      </div>
                      {(result.error || result.skip_reason) && (
                        <p className="mt-2 text-sm text-amber-700">{result.error ?? result.skip_reason}</p>
                      )}
                      <div className="mt-3 overflow-x-auto">
                        <table className="w-full min-w-[560px] text-left text-xs">
                          <thead className="text-slate-500">
                            <tr>
                              <th className="py-2 font-semibold">Tool</th>
                              <th className="py-2 font-semibold">Provider</th>
                              <th className="py-2 font-semibold">Status</th>
                              <th className="py-2 font-semibold">Duration</th>
                              <th className="py-2 font-semibold">Payload</th>
                            </tr>
                          </thead>
                          <tbody className="text-slate-700">
                            {result.tool_calls.length === 0 && (
                              <tr>
                                <td className="py-2" colSpan={5}>No tool calls recorded.</td>
                              </tr>
                            )}
                            {result.tool_calls.map((tool, index) => (
                              <tr key={`${tool.name}-${index}`} className="border-t border-slate-100">
                                <td className="py-2 font-medium">{tool.name}</td>
                                <td className="py-2">{tool.provider}</td>
                                <td className="py-2">{tool.status}</td>
                                <td className="py-2">{formatMs(tool.duration_ms)}</td>
                                <td className="py-2">{tool.payload_size_bytes ?? 0} bytes</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
