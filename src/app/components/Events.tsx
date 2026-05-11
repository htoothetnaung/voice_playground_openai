"use client";

import React, { useEffect, useRef, useState } from "react";

import { useEvent } from "@/app/contexts/EventContext";
import { LoggedEvent } from "@/app/types";

export interface EventsProps {
  isExpanded: boolean;
}

function Events({ isExpanded }: EventsProps) {
  const [prevEventLogs, setPrevEventLogs] = useState<LoggedEvent[]>([]);
  const eventLogsContainerRef = useRef<HTMLDivElement | null>(null);
  const { loggedEvents, toggleExpand } = useEvent();

  const getDirectionArrow = (direction: string) => {
    if (direction === "client") return { symbol: "▲", color: "#7c3aed" };
    if (direction === "server") return { symbol: "▼", color: "#059669" };
    return { symbol: "•", color: "#555" };
  };

  useEffect(() => {
    const hasNewEvent = loggedEvents.length > prevEventLogs.length;

    if (isExpanded && hasNewEvent && eventLogsContainerRef.current) {
      eventLogsContainerRef.current.scrollTop =
        eventLogsContainerRef.current.scrollHeight;
    }

    setPrevEventLogs(loggedEvents);
  }, [loggedEvents, isExpanded, prevEventLogs]);

  return (
    <div
      className={
        (isExpanded ? "w-[38%] overflow-auto opacity-100" : "w-0 overflow-hidden opacity-0") +
        " flex-col rounded-2xl border border-slate-200 bg-white shadow-sm transition-all duration-200 ease-in-out"
      }
      ref={eventLogsContainerRef}
    >
      {isExpanded && (
        <div>
          <div className="sticky top-0 z-10 flex items-center justify-between rounded-t-2xl border-b border-slate-200 bg-white px-6 py-4 text-base">
            <div className="flex flex-col">
              <span className="font-semibold text-slate-900">Logs</span>
              <span className="text-xs text-slate-500">
                Transport and session event trace
              </span>
            </div>
          </div>
          <div>
            {loggedEvents.map((log, idx) => {
              const arrowInfo = getDirectionArrow(log.direction);
              const isError =
                log.eventName.toLowerCase().includes("error") ||
                log.eventData?.response?.status_details?.error != null;

              return (
                <div
                  key={`${log.id}-${idx}`}
                  className="border-t border-slate-200 px-6 py-3 font-mono"
                >
                  <div
                    onClick={() => toggleExpand(log.id)}
                    className="flex cursor-pointer items-center justify-between gap-3"
                  >
                    <div className="flex flex-1 items-center gap-2">
                      <span style={{ color: arrowInfo.color }} className="text-xs">
                        {arrowInfo.symbol}
                      </span>
                      <span
                        className={
                          "flex-1 text-sm " +
                          (isError ? "text-rose-600" : "text-slate-800")
                        }
                      >
                        {log.eventName}
                      </span>
                    </div>
                    <div className="ml-1 whitespace-nowrap text-xs text-slate-500">
                      {log.timestamp}
                    </div>
                  </div>

                  {log.expanded && log.eventData && (
                    <div className="mt-2 text-left text-slate-800">
                      <pre className="mb-2 ml-1 whitespace-pre-wrap break-words border-l-2 border-slate-200 pl-2 font-mono text-xs">
                        {JSON.stringify(log.eventData, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default Events;
