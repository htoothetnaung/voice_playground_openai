"use-client";

import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import Image from "next/image";
import { ClipboardCopyIcon, DownloadIcon } from "@radix-ui/react-icons";

import { BreadcrumbType, TranscriptItem } from "@/app/types";
import { useTranscript } from "@/app/contexts/TranscriptContext";
import type { MicActivity } from "@/app/hooks/useBackendRealtimeSession";
import type { SessionStatus } from "@/app/types";

import { GuardrailChip } from "./GuardrailChip";

export interface TranscriptProps {
  userText: string;
  setUserText: (val: string) => void;
  onSendMessage: () => void;
  canSend: boolean;
  downloadRecording: () => void;
  canDownloadRecording?: boolean;
  sessionStatus: SessionStatus;
  isMicrophoneEnabled: boolean;
  micActivity: MicActivity;
  isAssistantSpeaking: boolean;
  activeAgentName?: string;
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
  sessionStatus,
  isMicrophoneEnabled,
  micActivity,
  isAssistantSpeaking,
  activeAgentName,
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

  const voiceStatus = getVoiceStatus({
    sessionStatus,
    isMicrophoneEnabled,
    micActivity,
    isAssistantSpeaking,
    activeAgentName,
  });

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

        <div className="border-b border-slate-200 bg-slate-950 px-4 py-4 text-white sm:px-6">
          <div className="flex min-w-0 items-center gap-4">
            <div className={`voice-orb ${voiceStatus.orbClass}`} aria-hidden="true">
              <span className="voice-orb-core" />
              <span className="voice-orb-ring" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-sm font-semibold ${voiceStatus.badgeClass}`}>
                  {voiceStatus.badge}
                </span>
                <span className="text-xs text-slate-400">{voiceStatus.caption}</span>
              </div>
              <div className="flex h-8 items-end gap-1.5" aria-label={voiceStatus.ariaLabel}>
                {voiceStatus.bars.map((height, index) => (
                  <span
                    key={index}
                    className={`voice-bar ${voiceStatus.barClass}`}
                    style={{
                      height,
                      animationDelay: `${index * 90}ms`,
                      animationPlayState: voiceStatus.isAnimated ? "running" : "paused",
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
          <style jsx>{`
            .voice-orb {
              position: relative;
              display: flex;
              height: 3rem;
              width: 3rem;
              flex-shrink: 0;
              align-items: center;
              justify-content: center;
              border-radius: 9999px;
              overflow: hidden;
              background:
                conic-gradient(from 20deg, #f8fafc, #475569, #020617, #f8fafc, #94a3b8, #020617, #f8fafc),
                radial-gradient(circle at 30% 30%, rgba(255,255,255,0.95), transparent 38%);
              box-shadow: inset 0 0 10px rgba(255,255,255,0.35), 0 0 0 1px rgba(255,255,255,0.08);
              animation: orb-spin 4s linear infinite;
            }
            .voice-orb-core {
              height: 0.8rem;
              width: 0.8rem;
              border-radius: 9999px;
              background: rgba(15, 23, 42, 0.75);
              box-shadow: 0 0 18px rgba(255,255,255,0.45);
              z-index: 2;
            }
            .voice-orb-ring {
              position: absolute;
              inset: 0.35rem;
              border-radius: 9999px;
              border: 1px solid rgba(255,255,255,0.22);
            }
            .voice-orb.is-speaking,
            .voice-orb.is-user-speaking {
              animation-duration: 1.4s;
            }
            .voice-orb.is-idle {
              animation-play-state: paused;
              opacity: 0.72;
            }
            .voice-bar {
              display: block;
              width: min(8%, 0.42rem);
              min-width: 0.22rem;
              border-radius: 9999px;
              opacity: 0.9;
              animation: voice-bounce 900ms ease-in-out infinite;
              transform-origin: bottom;
            }
            @keyframes orb-spin {
              to {
                transform: rotate(360deg);
              }
            }
            @keyframes voice-bounce {
              0%, 100% {
                transform: scaleY(0.55);
                opacity: 0.55;
              }
              50% {
                transform: scaleY(1);
                opacity: 1;
              }
            }
          `}</style>
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

type VoiceStatusInput = {
  sessionStatus: SessionStatus;
  isMicrophoneEnabled: boolean;
  micActivity: MicActivity;
  isAssistantSpeaking: boolean;
  activeAgentName?: string;
};

function getVoiceStatus({
  sessionStatus,
  isMicrophoneEnabled,
  micActivity,
  isAssistantSpeaking,
  activeAgentName,
}: VoiceStatusInput) {
  const agentLabel = activeAgentName ? `Agent: ${activeAgentName}` : "Voice agent";

  if (sessionStatus === "CONNECTING") {
    return {
      badge: "Connecting",
      caption: "Preparing the live voice session",
      ariaLabel: "Voice session connecting",
      badgeClass: "bg-slate-700 text-slate-100",
      barClass: "bg-slate-400",
      orbClass: "is-idle",
      bars: [8, 14, 20, 14, 8, 12, 16, 12],
      isAnimated: true,
    };
  }

  if (sessionStatus !== "CONNECTED") {
    return {
      badge: "Offline",
      caption: "Connect to start a voice call",
      ariaLabel: "Voice session offline",
      badgeClass: "bg-slate-800 text-slate-300",
      barClass: "bg-slate-600",
      orbClass: "is-idle",
      bars: [8, 8, 8, 8, 8, 8, 8, 8],
      isAnimated: false,
    };
  }

  if (isAssistantSpeaking) {
    return {
      badge: "Talking",
      caption: `${agentLabel} is responding`,
      ariaLabel: "Assistant is speaking",
      badgeClass: "bg-cyan-300 text-slate-950",
      barClass: "bg-cyan-300",
      orbClass: "is-speaking",
      bars: [12, 22, 30, 18, 26, 32, 20, 14],
      isAnimated: true,
    };
  }

  if (!isMicrophoneEnabled) {
    return {
      badge: "Mic off",
      caption: "Turn on the microphone to speak",
      ariaLabel: "Microphone disabled",
      badgeClass: "bg-slate-700 text-slate-100",
      barClass: "bg-slate-600",
      orbClass: "is-idle",
      bars: [8, 8, 8, 8, 8, 8, 8, 8],
      isAnimated: false,
    };
  }

  if (micActivity === "speech") {
    return {
      badge: "Listening",
      caption: "I can hear you speaking",
      ariaLabel: "User speech detected",
      badgeClass: "bg-emerald-300 text-slate-950",
      barClass: "bg-emerald-300",
      orbClass: "is-user-speaking",
      bars: [10, 18, 28, 24, 30, 20, 16, 12],
      isAnimated: true,
    };
  }

  if (micActivity === "noise") {
    return {
      badge: "Filtering",
      caption: "Background sound is being ignored",
      ariaLabel: "Background noise filtered",
      badgeClass: "bg-amber-300 text-slate-950",
      barClass: "bg-amber-300",
      orbClass: "is-idle",
      bars: [8, 10, 12, 10, 14, 10, 12, 8],
      isAnimated: true,
    };
  }

  return {
    badge: "Listening",
    caption: "Waiting for your voice",
    ariaLabel: "Listening for user voice",
    badgeClass: "bg-slate-700 text-slate-100",
    barClass: "bg-slate-400",
    orbClass: "is-idle",
    bars: [8, 10, 12, 10, 8, 10, 12, 10],
    isAnimated: true,
  };
}
