"use-client";

import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import Image from "next/image";
import { ClipboardCopyIcon, DownloadIcon } from "@radix-ui/react-icons";

import { BreadcrumbType, TranscriptItem } from "@/app/types";
import { useTranscript } from "@/app/contexts/TranscriptContext";

import { GuardrailChip } from "./GuardrailChip";

export interface TranscriptProps {
  userText: string;
  setUserText: (val: string) => void;
  onSendMessage: () => void;
  canSend: boolean;
  downloadRecording: () => void;
  canDownloadRecording?: boolean;
}

function getBreadcrumbPresentation(
  title: string,
  breadcrumbType?: BreadcrumbType
) {
  const normalizedType =
    breadcrumbType ||
    (title.startsWith("[supervisorAgent]") ? "supervisor" : "default");

  switch (normalizedType) {
    case "handoff":
      return {
        badge: "Handoff",
        wrapper: "border-violet-200 bg-violet-50/80 text-violet-900",
        badgeClass: "bg-violet-100 text-violet-700",
      };
    case "tool_call":
      return {
        badge: "Tool Start",
        wrapper: "border-amber-200 bg-amber-50/80 text-amber-950",
        badgeClass: "bg-amber-100 text-amber-700",
      };
    case "tool_result":
      return {
        badge: "Tool Result",
        wrapper: "border-emerald-200 bg-emerald-50/80 text-emerald-950",
        badgeClass: "bg-emerald-100 text-emerald-700",
      };
    case "guardrail":
      return {
        badge: "Guardrail",
        wrapper: "border-rose-200 bg-rose-50/80 text-rose-950",
        badgeClass: "bg-rose-100 text-rose-700",
      };
    case "audio":
      return {
        badge: "Audio",
        wrapper: "border-sky-200 bg-sky-50/80 text-sky-950",
        badgeClass: "bg-sky-100 text-sky-700",
      };
    case "ticket":
      return {
        badge: "Ticket",
        wrapper:
          "border-l-4 border-l-cyan-500 border-cyan-200 bg-[linear-gradient(135deg,#ecfeff_0%,#f8fafc_55%,#fff7ed_100%)] text-slate-950 shadow-sm",
        badgeClass: "bg-slate-950 text-cyan-100",
      };
    case "agent":
      return {
        badge: "Agent",
        wrapper: "border-slate-200 bg-slate-100/90 text-slate-900",
        badgeClass: "bg-white text-slate-600",
      };
    case "supervisor":
      return {
        badge: "Supervisor",
        wrapper: "border-fuchsia-200 bg-fuchsia-50/80 text-fuchsia-950",
        badgeClass: "bg-fuchsia-100 text-fuchsia-700",
      };
    case "session":
      return {
        badge: "Session",
        wrapper: "border-slate-200 bg-slate-50 text-slate-900",
        badgeClass: "bg-white text-slate-600",
      };
    default:
      return {
        badge: "Trace",
        wrapper: "border-slate-200 bg-white text-slate-900",
        badgeClass: "bg-slate-100 text-slate-600",
      };
  }
}

function Transcript({
  userText,
  setUserText,
  onSendMessage,
  canSend,
  downloadRecording,
  canDownloadRecording = true,
}: TranscriptProps) {
  const { transcriptItems, toggleTranscriptItemExpand } = useTranscript();
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const [prevLogs, setPrevLogs] = useState<TranscriptItem[]>([]);
  const [justCopied, setJustCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function scrollToBottom() {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }

  useEffect(() => {
    const hasNewMessage = transcriptItems.length > prevLogs.length;
    const hasUpdatedMessage = transcriptItems.some((newItem, index) => {
      const oldItem = prevLogs[index];
      return (
        oldItem &&
        (newItem.title !== oldItem.title || newItem.data !== oldItem.data)
      );
    });

    if (hasNewMessage || hasUpdatedMessage) {
      scrollToBottom();
    }

    setPrevLogs(transcriptItems);
  }, [transcriptItems, prevLogs]);

  useEffect(() => {
    if (canSend && inputRef.current) {
      inputRef.current.focus();
    }
  }, [canSend]);

  const handleCopyTranscript = async () => {
    if (!transcriptRef.current) return;
    try {
      await navigator.clipboard.writeText(transcriptRef.current.innerText);
      setJustCopied(true);
      setTimeout(() => setJustCopied(false), 1500);
    } catch (error) {
      console.error("Failed to copy transcript:", error);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="sticky top-0 z-10 flex flex-col gap-3 rounded-t-2xl border-b border-slate-200 bg-white px-4 py-3 text-base sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-4">
          <div className="flex min-w-0 flex-col">
            <span className="font-semibold text-slate-900">Transcript</span>
            <span className="text-xs text-slate-500">
              Live call flow, handoffs, guardrails, and tool activity
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:gap-x-2">
            <button
              onClick={handleCopyTranscript}
              className="flex items-center justify-center gap-x-1 rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-700 hover:bg-slate-200 sm:w-24"
            >
              <ClipboardCopyIcon />
              {justCopied ? "Copied!" : "Copy"}
            </button>
            <button
              onClick={downloadRecording}
              disabled={!canDownloadRecording}
              className="flex items-center justify-center gap-x-1 rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50 sm:w-40"
            >
              <DownloadIcon />
              <span>{canDownloadRecording ? "Download Audio" : "Download"}</span>
            </button>
          </div>
        </div>

        <div
          ref={transcriptRef}
          className="flex h-full flex-col gap-y-4 overflow-auto bg-[radial-gradient(circle_at_top,_rgba(226,232,240,0.18),_transparent_32%)] px-3 py-3 sm:px-5 sm:py-4"
        >
          {[...transcriptItems]
            .sort((a, b) => a.createdAtMs - b.createdAtMs)
            .map((item) => {
              const {
                itemId,
                type,
                role,
                data,
                expanded,
                timestamp,
                title = "",
                isHidden,
                guardrailResult,
                breadcrumbType,
              } = item;

              if (isHidden) {
                return null;
              }

              if (type === "MESSAGE") {
                const isUser = role === "user";
                const containerClasses = `flex flex-col justify-end ${
                  isUser ? "items-end" : "items-start"
                }`;
                const bubbleBase = `max-w-[min(42rem,92vw)] border p-3 shadow-sm sm:p-4 ${
                  isUser
                    ? "border-slate-900 bg-slate-900 text-slate-50"
                    : "border-slate-200 bg-slate-50 text-slate-900"
                }`;
                const isBracketedMessage =
                  title.startsWith("[") && title.endsWith("]");
                const messageStyle = isBracketedMessage
                  ? "italic text-slate-400"
                  : "";
                const displayTitle = isBracketedMessage
                  ? title.slice(1, -1)
                  : title;

                return (
                  <div key={itemId} className={containerClasses}>
                    <div className="max-w-[min(42rem,92vw)]">
                      <div
                        className={`${bubbleBase} rounded-t-2xl ${
                          guardrailResult ? "" : "rounded-b-2xl"
                        }`}
                      >
                        <div
                          className={`font-mono text-xs ${
                            isUser ? "text-slate-400" : "text-slate-500"
                          }`}
                        >
                          {timestamp}
                        </div>
                        <div className={`whitespace-pre-wrap ${messageStyle}`}>
                          <ReactMarkdown>{displayTitle}</ReactMarkdown>
                        </div>
                      </div>
                      {guardrailResult && (
                        <div className="rounded-b-2xl border border-t-0 border-slate-200 bg-slate-100 px-4 py-3">
                          <GuardrailChip guardrailResult={guardrailResult} />
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              if (type === "BREADCRUMB") {
                const presentation = getBreadcrumbPresentation(
                  title,
                  breadcrumbType
                );
                return (
                  <div
                    key={itemId}
                    className="flex flex-col items-start justify-start text-sm text-slate-500"
                  >
                    <span className="mb-1 font-mono text-xs">{timestamp}</span>
                    <div
                      className={`flex w-full items-start gap-2 rounded-2xl border px-3 py-3 font-mono text-xs sm:gap-3 sm:px-4 sm:text-sm ${presentation.wrapper} ${
                        data ? "cursor-pointer" : ""
                      }`}
                      onClick={() => data && toggleTranscriptItemExpand(itemId)}
                    >
                      <div className="flex min-w-0 flex-1 items-start gap-3">
                        <span
                          className={`mt-0.5 rounded-full px-2 py-1 text-[10px] font-semibold uppercase ${presentation.badgeClass}`}
                        >
                          {presentation.badge}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="break-words">{title}</div>
                          {data && (
                            <div className="mt-1 text-[11px] text-slate-500">
                              Click to {expanded ? "collapse" : "expand"} details
                            </div>
                          )}
                        </div>
                      </div>
                      {data && (
                        <span
                          className={`select-none font-mono text-slate-400 transition-transform duration-200 ${
                            expanded ? "rotate-90" : "rotate-0"
                          }`}
                        >
                          &gt;
                        </span>
                      )}
                    </div>
                    {expanded && data && (
                      <div className="w-full text-left text-slate-800">
                        <pre className="mb-2 mt-2 ml-3 whitespace-pre-wrap break-words border-l-2 border-slate-200 pl-3 font-mono text-xs">
                          {JSON.stringify(data, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div
                  key={itemId}
                  className="flex justify-center font-mono text-sm italic text-slate-500"
                >
                  Unknown item type: {type}{" "}
                  <span className="ml-2 text-xs">{timestamp}</span>
                </div>
              );
            })}
        </div>
      </div>

      <div className="flex flex-shrink-0 items-center gap-x-2 rounded-b-2xl border-t border-slate-200 bg-white p-3 sm:p-4">
        <input
          ref={inputRef}
          type="text"
          value={userText}
          onChange={(e) => setUserText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSend) {
              onSendMessage();
            }
          }}
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-slate-300"
          placeholder="Type a message..."
        />
        <button
          onClick={onSendMessage}
          disabled={!canSend || !userText.trim()}
          className="rounded-full bg-slate-900 px-3 py-3 text-white shadow-sm disabled:opacity-50"
        >
          <Image src="/arrow.svg" alt="Send" width={24} height={24} />
        </button>
      </div>
    </div>
  );
}

export default Transcript;
