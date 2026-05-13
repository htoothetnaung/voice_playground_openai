"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import {
  ActivityLogIcon,
  ArrowRightIcon,
  CheckCircledIcon,
  DashboardIcon,
  ExclamationTriangleIcon,
  LightningBoltIcon,
  ReaderIcon,
} from "@radix-ui/react-icons";

type AdminSession = {
  session_id: string;
  trace_id?: string;
  architecture?: string;
  starting_agent?: string;
  status?: string;
  outcome_ticket_kind?: string;
  outcome_ticket_id?: string;
  last_ticket_id?: string;
  created_at?: string;
  updated_at?: string;
};

type AdminTicket = {
  ticket_id: string;
  kind: string;
  title: string;
  summary?: string;
  priority?: string;
  status?: string;
};

type AdminTranscript = {
  item_id: string;
  role?: string;
  text?: string;
};

type AdminEvent = {
  event_id?: string;
  event_name: string;
  direction?: string;
  created_at?: string;
  event_data?: Record<string, unknown>;
};

type SessionsResponse = {
  sessions: AdminSession[];
};

type SessionDetail = {
  session: AdminSession;
  tickets: AdminTicket[];
  transcripts: AdminTranscript[];
  events: AdminEvent[];
};

const emptySessions: AdminSession[] = [
  {
    session_id: "waiting-for-first-call",
    architecture: "cascaded_pipeline",
    starting_agent: "callcenteragent",
    status: "ready",
    outcome_ticket_kind: "pending",
    updated_at: "No session records yet",
  },
];

const navItems: Array<{
  label: string;
  Icon: ComponentType<{ className?: string }>;
}> = [
  { label: "Command overview", Icon: DashboardIcon },
  { label: "Session review", Icon: ReaderIcon },
  { label: "Ticket queue", Icon: ExclamationTriangleIcon },
  { label: "Runtime signals", Icon: ActivityLogIcon },
];

function formatDate(value?: string) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function outcomeLabel(kind?: string) {
  if (kind === "resolved") return "Resolved";
  if (kind === "needs_attention") return "Needs attention";
  if (kind === "field_service_action") return "Field action";
  return "Pending";
}

export default function AdminPage() {
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadSessions() {
      try {
        const response = await fetch("/api/admin/sessions?limit=25", {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Session API returned ${response.status}`);
        }
        const payload = (await response.json()) as SessionsResponse;
        if (!cancelled) {
          setSessions(payload.sessions ?? []);
          setSelectedSessionId((current) => current ?? payload.sessions?.[0]?.session_id ?? null);
          setLoadError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Unable to load sessions");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedSessionId || selectedSessionId === "waiting-for-first-call") {
      setSessionDetail(null);
      return;
    }

    let cancelled = false;
    const sessionId = selectedSessionId;
    async function loadSessionDetail() {
      setIsDetailLoading(true);
      try {
        const response = await fetch(
          `/api/admin/sessions/${encodeURIComponent(sessionId)}`,
          { cache: "no-store" },
        );
        if (!response.ok) {
          throw new Error(`Session detail returned ${response.status}`);
        }
        const payload = (await response.json()) as SessionDetail;
        if (!cancelled) {
          setSessionDetail(payload);
          setDetailError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setSessionDetail(null);
          setDetailError(error instanceof Error ? error.message : "Unable to load session detail");
        }
      } finally {
        if (!cancelled) setIsDetailLoading(false);
      }
    }

    void loadSessionDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedSessionId]);

  const visibleSessions = sessions.length > 0 ? sessions : emptySessions;
  const selectedSession =
    visibleSessions.find((session) => session.session_id === selectedSessionId) ??
    visibleSessions[0];
  const detailTickets = sessionDetail?.tickets ?? [];
  const detailTranscripts = sessionDetail?.transcripts ?? [];
  const detailEvents = sessionDetail?.events ?? [];

  const metrics = useMemo(() => {
    const resolved = sessions.filter((session) => session.outcome_ticket_kind === "resolved").length;
    const attention = sessions.filter((session) => session.outcome_ticket_kind === "needs_attention").length;
    const active = sessions.filter((session) => session.status === "active").length;
    return [
      { label: "Stored Sessions", value: sessions.length, caption: "Mongo-backed reviews" },
      { label: "Needs Attention", value: attention, caption: "Human follow-up queue" },
      { label: "Resolved", value: resolved, caption: "Closed outcome tickets" },
      { label: "Live Calls", value: active, caption: "Active WebSocket sessions" },
    ];
  }, [sessions]);

  return (
    <main className="min-h-screen bg-[#f5f3ee] text-[#151a1f]">
      <div className="grid min-h-screen lg:grid-cols-[280px_1fr]">
        <aside className="flex flex-col justify-between bg-[#121820] px-6 py-6 text-white">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#e7b75f] text-[#121820]">
                <DashboardIcon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold">Atenxion</p>
                <p className="text-xs text-slate-400">Operations Console</p>
              </div>
            </div>

            <nav className="mt-10 space-y-2 text-sm">
              {navItems.map(({ label, Icon }) => (
                <div key={label} className="flex items-center gap-3 rounded-lg px-3 py-2 text-slate-300">
                  <Icon className="h-4 w-4 text-[#7bd6c8]" />
                  {label}
                </div>
              ))}
            </nav>
          </div>

          <Link
            href="/"
            className="flex items-center justify-between rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200"
          >
            Call Center Lab
            <ArrowRightIcon />
          </Link>
        </aside>

        <section className="min-w-0">
          <header className="border-b border-[#ded8cc] bg-[#fbfaf7] px-8 py-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#80735f]">
                  Customer Operations
                </p>
                <h1 className="mt-2 text-3xl font-semibold text-[#151a1f]">
                  Session Review Board
                </h1>
              </div>
              <div className="rounded-lg border border-[#d5cec0] bg-white px-4 py-3 text-sm text-[#4e5a5a]">
                {isLoading
                  ? "Loading Mongo sessions..."
                  : loadError
                    ? "Offline snapshot"
                    : "Mongo session feed connected"}
              </div>
            </div>
          </header>

          <div className="space-y-5 px-8 py-6">
            <section className="grid gap-3 md:grid-cols-4">
              {metrics.map((metric) => (
                <div key={metric.label} className="rounded-lg border border-[#ded8cc] bg-white px-4 py-4">
                  <p className="text-xs font-semibold uppercase text-[#80735f]">{metric.label}</p>
                  <p className="mt-2 text-3xl font-semibold">{metric.value}</p>
                  <p className="mt-1 text-sm text-[#65716d]">{metric.caption}</p>
                </div>
              ))}
            </section>

            <section className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="rounded-lg border border-[#d8d0c1] bg-white">
                <div className="flex items-center justify-between border-b border-[#e5dfd4] px-5 py-4">
                  <div>
                    <h2 className="font-semibold">Recent Conversation Sessions</h2>
                    <p className="text-sm text-[#65716d]">
                      Click a session to inspect its tickets, transcript, and runtime logs.
                    </p>
                  </div>
                  <LightningBoltIcon className="h-5 w-5 text-[#be6b2b]" />
                </div>

                <div className="divide-y divide-[#ebe5db]">
                  {visibleSessions.map((session) => {
                    const needsAttention = session.outcome_ticket_kind === "needs_attention";
                    const resolved = session.outcome_ticket_kind === "resolved";
                    const selected = selectedSession.session_id === session.session_id;
                    return (
                      <button
                        type="button"
                        key={session.session_id}
                        onClick={() => setSelectedSessionId(session.session_id)}
                        className={
                          "grid w-full gap-3 px-5 py-4 text-left transition md:grid-cols-[1fr_150px_150px] " +
                          (selected ? "bg-[#f2eee6]" : "hover:bg-[#fbf8f1]")
                        }
                      >
                        <div className="min-w-0">
                          <p className="truncate font-mono text-sm text-[#1d5960]">
                            {session.session_id}
                          </p>
                          <p className="mt-1 text-sm text-[#65716d]">
                            {session.architecture ?? "cascaded_pipeline"} /{" "}
                            {session.starting_agent ?? "callcenteragent"}
                          </p>
                        </div>
                        <div
                          className={
                            "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium " +
                            (needsAttention
                              ? "bg-[#fff1e8] text-[#9b3f21]"
                              : resolved
                                ? "bg-[#eaf7ef] text-[#236341]"
                                : "bg-[#eef3f4] text-[#46616a]")
                          }
                        >
                          {resolved ? <CheckCircledIcon /> : <ExclamationTriangleIcon />}
                          {outcomeLabel(session.outcome_ticket_kind)}
                        </div>
                        <div className="text-sm text-[#65716d]">
                          <span className="block font-medium text-[#151a1f]">
                            {session.status ?? "pending"}
                          </span>
                          {formatDate(session.updated_at)}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-5">
                <section className="rounded-lg border border-[#d8d0c1] bg-[#151a1f] text-white">
                  <div className="border-b border-white/10 px-5 py-4">
                    <h2 className="font-semibold">Selected Session</h2>
                    <p className="mt-1 text-sm text-slate-400">
                      {isDetailLoading
                        ? "Loading session detail..."
                        : detailError
                          ? detailError
                          : "Tickets, transcript turns, and normalized logs."}
                    </p>
                  </div>
                  <div className="space-y-4 px-5 py-5 text-sm">
                    <div>
                      <p className="text-slate-400">Session</p>
                      <p className="mt-1 break-all font-mono text-[#7bd6c8]">
                        {selectedSession.session_id}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-slate-400">Outcome</p>
                        <p className="mt-1">{outcomeLabel(selectedSession.outcome_ticket_kind)}</p>
                      </div>
                      <div>
                        <p className="text-slate-400">Ticket</p>
                        <p className="mt-1 font-mono text-xs">
                          {selectedSession.outcome_ticket_id ?? selectedSession.last_ticket_id ?? "Pending"}
                        </p>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="rounded-lg border border-[#d8d0c1] bg-white">
                  <div className="border-b border-[#e5dfd4] px-5 py-4">
                    <h2 className="font-semibold">Conversation Detail</h2>
                  </div>

                  <div className="max-h-[34rem] space-y-5 overflow-auto px-5 py-5">
                    <DetailTickets tickets={detailTickets} />
                    <DetailTranscript transcripts={detailTranscripts} />
                    <DetailEvents events={detailEvents} />
                  </div>
                </section>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}

function DetailTickets({ tickets }: { tickets: AdminTicket[] }) {
  return (
    <div>
      <SectionHeader label="Tickets" count={tickets.length} />
      {tickets.length === 0 ? (
        <EmptyDetail>No tickets recorded for this session yet.</EmptyDetail>
      ) : (
        <div className="space-y-2">
          {tickets.map((ticket) => (
            <div key={ticket.ticket_id} className="rounded-lg border border-[#d8d0c1] px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{ticket.title}</p>
                  <p className="mt-1 text-sm text-[#65716d]">{ticket.summary}</p>
                </div>
                <span className="rounded-md bg-[#151a1f] px-2 py-1 text-xs font-medium text-[#7bd6c8]">
                  {ticket.status ?? "open"}
                </span>
              </div>
              <p className="mt-2 font-mono text-xs text-[#1d5960]">
                {ticket.ticket_id} / {ticket.kind} / {ticket.priority ?? "normal"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailTranscript({ transcripts }: { transcripts: AdminTranscript[] }) {
  return (
    <div>
      <SectionHeader label="Transcript" count={transcripts.length} />
      {transcripts.length === 0 ? (
        <EmptyDetail>No transcript records found.</EmptyDetail>
      ) : (
        <div className="space-y-2">
          {transcripts.map((turn) => (
            <div
              key={turn.item_id}
              className={
                "rounded-lg px-3 py-3 text-sm " +
                (turn.role === "user"
                  ? "bg-[#eef3f4] text-[#203239]"
                  : "bg-[#f8f3ea] text-[#2d2821]")
              }
            >
              <p className="mb-1 text-xs font-semibold uppercase text-[#80735f]">
                {turn.role ?? "message"}
              </p>
              <p className="whitespace-pre-wrap">{turn.text || "[No text]"}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailEvents({ events }: { events: AdminEvent[] }) {
  const recentEvents = events.slice(-25);

  return (
    <div>
      <SectionHeader label="Logs" count={events.length} />
      {events.length === 0 ? (
        <EmptyDetail>No runtime logs found.</EmptyDetail>
      ) : (
        <div className="space-y-2">
          {recentEvents.map((event, index) => (
            <details
              key={event.event_id ?? `${event.event_name}-${event.created_at ?? "undated"}-${index}`}
              className="rounded-lg border border-[#ebe5db] bg-[#fbfaf7] px-3 py-2 text-sm"
            >
              <summary className="cursor-pointer font-mono text-xs text-[#1d5960]">
                {event.direction ?? "server"} / {event.event_name}
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-[#3d4643]">
                {JSON.stringify(event.event_data ?? {}, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h3 className="text-sm font-semibold uppercase text-[#80735f]">{label}</h3>
      <span className="text-xs text-[#65716d]">{count}</span>
    </div>
  );
}

function EmptyDetail({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-[#ebe5db] bg-[#fbfaf7] px-3 py-3 text-sm text-[#65716d]">
      {children}
    </p>
  );
}
