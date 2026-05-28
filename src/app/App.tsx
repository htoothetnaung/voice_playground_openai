"use client";
import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { v4 as uuidv4 } from "uuid";
import {
  ActivityLogIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DashboardIcon,
  LightningBoltIcon,
} from "@radix-ui/react-icons";

import { SessionStatus } from "@/app/types";
import { allAgentSets, defaultAgentSetKey } from "@/app/agentConfigs";
import type { AgentOption } from "@/app/agentConfigs/types";
import { useEvent } from "@/app/contexts/EventContext";
import { useTranscript } from "@/app/contexts/TranscriptContext";

import Transcript from "./components/Transcript";
import Events from "./components/Events";
import BottomToolbar from "./components/BottomToolbar";
import useAudioDownload from "./hooks/useAudioDownload";
import { useFillerAudio } from "./hooks/useFillerAudio";
import { useBackendRealtimeSession } from "./hooks/useBackendRealtimeSession";

function App() {
  const searchParams = useSearchParams()!;
  const urlCodec = searchParams.get("codec") || "opus";
  const selectedArchitecture =
    searchParams.get("architecture") || "cascaded_pipeline";
  const { addTranscriptMessage, addTranscriptBreadcrumb } = useTranscript();
  const { logClientEvent } = useEvent();
  const [selectedAgentName, setSelectedAgentName] = useState<string>("");
  const [selectedAgentConfigSet, setSelectedAgentConfigSet] = useState<
    AgentOption[] | null
  >(null);
  const [sessionStatus, setSessionStatus] =
    useState<SessionStatus>("DISCONNECTED");
  const [isEventsPaneExpanded, setIsEventsPaneExpanded] =
    useState<boolean>(true);
  const [userText, setUserText] = useState<string>("");
  const [isMicrophoneEnabled, setIsMicrophoneEnabled] =
    useState<boolean>(true);
  const [areMobileSettingsOpen, setAreMobileSettingsOpen] =
    useState<boolean>(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] =
    useState<boolean>(false);
  const [isAudioPlaybackEnabled, setIsAudioPlaybackEnabled] =
    useState<boolean>(true);
  const [areFillerSoundsEnabled, setAreFillerSoundsEnabled] =
    useState<boolean>(true);
  const [isAssistantSpeaking, setIsAssistantSpeaking] =
    useState<boolean>(false);
  const {
    playTransfer,
    stopToolWait,
    stopAll,
    setAssistantAudioActive,
  } = useFillerAudio(areFillerSoundsEnabled);
  const handoffTriggeredRef = useRef(false);

  const {
    connect,
    disconnect,
    sendUserText,
    sendEvent,
    interrupt,
    mute,
    setMicrophoneEnabled: setBackendMicrophoneEnabled,
    micMeter,
  } =
    useBackendRealtimeSession({
      onConnectionChange: (s) => setSessionStatus(s as SessionStatus),
      onAgentHandoff: (agentName: string) => {
        handoffTriggeredRef.current = true;
        stopToolWait();
        addTranscriptBreadcrumb(`Agent handoff to ${agentName}`, {
          targetAgent: agentName,
          _breadcrumbType: "handoff",
        });
        setSelectedAgentName(agentName);
      },
      onTransferAudioStart: (agentName?: string, durationMs?: number) => {
        stopToolWait();
        addTranscriptBreadcrumb("Filler audio: transfer ringing", {
          state: "started",
          targetAgent: agentName,
          durationMs,
          _breadcrumbType: "audio",
        });
        playTransfer();
      },
      onTransferAudioEnd: (agentName?: string) => {
        addTranscriptBreadcrumb("Filler audio: transfer window complete", {
          state: "looping_until_agent_audio",
          targetAgent: agentName,
          _breadcrumbType: "audio",
        });
      },
      onAgentToolStart: (toolName: string) => {
        addTranscriptBreadcrumb(`Tool running: ${toolName}`, {
          toolName,
          _breadcrumbType: "tool_call",
        });
      },
      onAgentToolEnd: () => {
        stopToolWait();
      },
      onAssistantSpeechStart: () => {
        setIsAssistantSpeaking(true);
        setAssistantAudioActive(true);
      },
      onAssistantSpeechEnd: () => {
        setIsAssistantSpeaking(false);
        setAssistantAudioActive(false);
      },
    });

  const { stopRecording, downloadRecording } = useAudioDownload();

  const sendClientEvent = (eventObj: any, eventNameSuffix = "") => {
    try {
      sendEvent(eventObj);
      logClientEvent(eventObj, eventNameSuffix);
    } catch (err) {
      console.error("Failed to send via backend realtime socket", err);
    }
  };

  useEffect(() => {
    let finalAgentConfig = searchParams.get("agentConfig");
    if (!finalAgentConfig || !allAgentSets[finalAgentConfig]) {
      finalAgentConfig = defaultAgentSetKey;
      const url = new URL(window.location.toString());
      url.searchParams.set("agentConfig", finalAgentConfig);
      window.location.replace(url.toString());
      return;
    }

    const agents = allAgentSets[finalAgentConfig];
    const agentKeyToUse = agents[0]?.name || "";

    setSelectedAgentName(agentKeyToUse);
    setSelectedAgentConfigSet(agents);
  }, [searchParams]);

  useEffect(() => {
    if (selectedAgentName && sessionStatus === "DISCONNECTED") {
      void connectToRealtime();
    }
  }, [selectedAgentName]);

  useEffect(() => {
    if (
      sessionStatus === "CONNECTED" &&
      selectedAgentConfigSet &&
      selectedAgentName
    ) {
      const currentAgent = selectedAgentConfigSet.find(
        (a) => a.name === selectedAgentName
      );
      addTranscriptBreadcrumb(`Agent: ${selectedAgentName}`, {
        handoffDescription: currentAgent?.handoffDescription,
        _breadcrumbType: handoffTriggeredRef.current ? "handoff" : "agent",
      });
      updateSession(!handoffTriggeredRef.current);
      handoffTriggeredRef.current = false;
    }
  }, [selectedAgentConfigSet, selectedAgentName, sessionStatus]);

  const connectToRealtime = async () => {
    const agentSetKey = searchParams.get("agentConfig") || "default";
    if (!allAgentSets[agentSetKey]) return;
    if (sessionStatus !== "DISCONNECTED") return;

    setSessionStatus("CONNECTING");

    try {
      await connect({
        agentName: selectedAgentName,
        architecture: selectedArchitecture,
      });
    } catch (err) {
      console.error("Error connecting via backend runtime:", err);
      setSessionStatus("DISCONNECTED");
    }
  };

  const disconnectFromRealtime = () => {
    setAssistantAudioActive(false);
    setIsAssistantSpeaking(false);
    stopAll();
    disconnect();
    setSessionStatus("DISCONNECTED");
  };

  const sendSimulatedUserMessage = (text: string) => {
    const id = uuidv4().slice(0, 32);
    addTranscriptMessage(id, "user", text, true);

    sendClientEvent({
      type: "conversation.item.create",
      item: {
        id,
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    });
    sendClientEvent(
      { type: "response.create" },
      "(simulated user text message)"
    );
  };

  const updateSession = (shouldTriggerResponse: boolean = false) => {
    sendEvent({
      type: "session.update",
      session: {
        type: "realtime",
        audio: {
          input: {
            turn_detection: {
              type: "server_vad",
              threshold: 0.9,
              prefix_padding_ms: 300,
              silence_duration_ms: 500,
              create_response: true,
            },
          },
        },
      },
    });

    if (shouldTriggerResponse) {
      sendSimulatedUserMessage("hi");
    }
  };

  const handleSendTextMessage = () => {
    if (!userText.trim()) return;
    interrupt();

    try {
      sendUserText(userText.trim());
    } catch (err) {
      console.error("Failed to send via SDK", err);
    }

    setUserText("");
  };

  const onToggleConnection = () => {
    if (sessionStatus === "CONNECTED" || sessionStatus === "CONNECTING") {
      disconnectFromRealtime();
      setSessionStatus("DISCONNECTED");
    } else {
      void connectToRealtime();
    }
  };

  const handleAgentChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newAgentConfig = e.target.value;
    const url = new URL(window.location.toString());
    url.searchParams.set("agentConfig", newAgentConfig);
    window.location.replace(url.toString());
  };

  const handleSelectedAgentChange = (
    e: React.ChangeEvent<HTMLSelectElement>
  ) => {
    const newAgentName = e.target.value;
    disconnectFromRealtime();
    setSelectedAgentName(newAgentName);
  };

  const handleCodecChange = (newCodec: string) => {
    const url = new URL(window.location.toString());
    url.searchParams.set("codec", newCodec);
    window.location.replace(url.toString());
  };

  const handleArchitectureChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    disconnectFromRealtime();
    const url = new URL(window.location.toString());
    url.searchParams.set("architecture", e.target.value);
    window.location.replace(url.toString());
  };

  useEffect(() => {
    const storedMicrophoneEnabled = localStorage.getItem("microphoneEnabled");
    if (storedMicrophoneEnabled) {
      setIsMicrophoneEnabled(storedMicrophoneEnabled === "true");
    }
    const storedLogsExpanded = localStorage.getItem("logsExpanded");
    if (storedLogsExpanded) {
      setIsEventsPaneExpanded(storedLogsExpanded === "true");
    }
    const storedAudioPlaybackEnabled = localStorage.getItem(
      "audioPlaybackEnabled"
    );
    if (storedAudioPlaybackEnabled) {
      setIsAudioPlaybackEnabled(storedAudioPlaybackEnabled === "true");
    }
    const storedFillerSoundsEnabled = localStorage.getItem(
      "fillerSoundsEnabled"
    );
    if (storedFillerSoundsEnabled) {
      setAreFillerSoundsEnabled(storedFillerSoundsEnabled === "true");
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("microphoneEnabled", isMicrophoneEnabled.toString());
  }, [isMicrophoneEnabled]);

  useEffect(() => {
    setBackendMicrophoneEnabled(isMicrophoneEnabled);
  }, [isMicrophoneEnabled, setBackendMicrophoneEnabled]);

  useEffect(() => {
    localStorage.setItem("logsExpanded", isEventsPaneExpanded.toString());
  }, [isEventsPaneExpanded]);

  useEffect(() => {
    localStorage.setItem(
      "audioPlaybackEnabled",
      isAudioPlaybackEnabled.toString()
    );
  }, [isAudioPlaybackEnabled]);

  useEffect(() => {
    localStorage.setItem(
      "fillerSoundsEnabled",
      areFillerSoundsEnabled.toString()
    );
  }, [areFillerSoundsEnabled]);

  useEffect(() => {
    if (sessionStatus === "DISCONNECTED") {
      setAssistantAudioActive(false);
      setIsAssistantSpeaking(false);
      stopAll();
    }
  }, [sessionStatus, setAssistantAudioActive, stopAll]);

  useEffect(() => {
    try {
      mute(!isAudioPlaybackEnabled);
    } catch (err) {
      console.warn("Failed to toggle backend playback mute", err);
    }
  }, [isAudioPlaybackEnabled, mute]);

  useEffect(() => {
    if (sessionStatus === "CONNECTED") {
      try {
        mute(!isAudioPlaybackEnabled);
      } catch (err) {
        console.warn("mute sync after backend connect failed", err);
      }
    }
  }, [sessionStatus, isAudioPlaybackEnabled, mute]);

  useEffect(() => {
    return () => {
      stopRecording();
    };
  }, [stopRecording]);

  const agentSetKey = searchParams.get("agentConfig") || "default";

  return (
    <div className="relative flex h-[100dvh] min-h-[100dvh] bg-slate-100 text-base text-slate-800">
      <aside
        className={
          "hidden flex-col justify-between border-r border-slate-800 bg-slate-950 py-5 text-white transition-all lg:flex " +
          (isSidebarCollapsed ? "w-[84px] px-3" : "w-[260px] px-5")
        }
      >
        <div>
          <div
            className={
              "flex items-center gap-3 " +
              (isSidebarCollapsed ? "justify-center" : "")
            }
          >
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-cyan-300 text-slate-950">
              <Image
                src="/atenxion_logo.png"
                alt="Atenxion Logo"
                width={24}
                height={24}
              />
            </div>
            <div className={isSidebarCollapsed ? "hidden" : "min-w-0"}>
              <p className="truncate text-sm font-semibold">Atenxion Lab</p>
              <p className="text-xs text-slate-400">Voice operations</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setIsSidebarCollapsed((collapsed) => !collapsed)}
            className={
              "mt-6 flex h-9 w-full items-center justify-center rounded-lg border border-white/15 text-slate-200 transition hover:bg-white/10 " +
              (isSidebarCollapsed ? "" : "gap-2")
            }
            aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isSidebarCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
            <span className={isSidebarCollapsed ? "hidden" : "text-sm font-medium"}>
              Collapse
            </span>
          </button>

          <nav className="mt-8 space-y-2 text-sm text-slate-300">
            <Link
              href="/"
              className={
                "flex items-center gap-3 rounded-lg bg-white/10 px-3 py-2 " +
                (isSidebarCollapsed ? "justify-center" : "")
              }
            >
              <DashboardIcon className="h-4 w-4 text-cyan-300" />
              <span className={isSidebarCollapsed ? "hidden" : ""}>
                Call Center Lab
              </span>
            </Link>
            <Link
              href="/stress-lab"
              className={
                "flex items-center gap-3 rounded-lg px-3 py-2 transition hover:bg-white/10 " +
                (isSidebarCollapsed ? "justify-center" : "")
              }
            >
              <LightningBoltIcon className="h-4 w-4 text-cyan-300" />
              <span className={isSidebarCollapsed ? "hidden" : ""}>
                Stress Lab
              </span>
            </Link>
            <Link
              href="/admin"
              className={
                "flex items-center gap-3 rounded-lg px-3 py-2 transition hover:bg-white/10 " +
                (isSidebarCollapsed ? "justify-center" : "")
              }
            >
              <ActivityLogIcon className="h-4 w-4 text-cyan-300" />
              <span className={isSidebarCollapsed ? "hidden" : ""}>
                Admin Console
              </span>
            </Link>
          </nav>
        </div>

        <div
          className={
            "rounded-lg border border-white/15 p-3 text-xs text-slate-300 " +
            (isSidebarCollapsed ? "hidden" : "")
          }
        >
          <p className="font-semibold text-white">Realtime voice</p>
          <p className="mt-1 leading-5 text-slate-400">
            Handoffs, tools, transcript, and call audio.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
      <div className="border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-6 lg:py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <div
              className="flex min-w-0 cursor-pointer items-center gap-3"
              onClick={() => window.location.reload()}
            >
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-100 sm:h-11 sm:w-11">
                <Image
                  src="/atenxion_logo.png"
                  alt="Atenxion Logo"
                  width={28}
                  height={28}
                />
              </div>
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-base font-semibold text-slate-900 sm:text-lg">
                  Atenxion Call Center Lab
                </span>
                <span className="line-clamp-1 text-xs font-normal leading-5 text-slate-500 sm:text-sm">
                  Realtime handoffs, tool calls, guardrails, and call-floor audio cues
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setAreMobileSettingsOpen((open) => !open)}
              aria-expanded={areMobileSettingsOpen}
              className="inline-flex h-10 flex-shrink-0 items-center justify-center gap-1 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm lg:hidden"
            >
              <span>Setup</span>
              <ChevronDownIcon
                className={
                  "transition-transform " +
                  (areMobileSettingsOpen ? "rotate-180" : "rotate-0")
                }
              />
            </button>
          </div>

          <div
            className={
              "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:flex xl:items-center xl:gap-4 " +
              (areMobileSettingsOpen ? "grid" : "hidden lg:flex")
            }
          >
            <div className="flex items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 sm:justify-start xl:py-1">
              Telecom support simulation
            </div>
            <div className="min-w-0">
              <label className="mb-1 block text-xs font-semibold uppercase text-slate-500">
                Architecture
              </label>
              <div className="relative">
                <select
                  value={selectedArchitecture}
                  onChange={handleArchitectureChange}
                  className="w-full appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                >
                  <option value="openai_native">OpenAI native realtime</option>
                  <option value="cascaded_pipeline">Deepgram + GPT + ElevenLabs</option>
                  <option value="elevenlabs_pipeline">ElevenLabs + GPT + ElevenLabs</option>
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-slate-500">
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 10.44l3.71-3.21a.75.75 0 111.04 1.08l-4.25 3.65a.75.75 0 01-1.04 0L5.21 8.27a.75.75 0 01.02-1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
              </div>
            </div>
            <div className="min-w-0">
              <label className="mb-1 block text-xs font-semibold uppercase text-slate-500">
                Scenario
              </label>
              <div className="relative">
                <select
                  value={agentSetKey}
                  onChange={handleAgentChange}
                  className="w-full appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                >
                  {Object.keys(allAgentSets).map((agentKey) => (
                    <option key={agentKey} value={agentKey}>
                      {agentKey}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-slate-500">
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 10.44l3.71-3.21a.75.75 0 111.04 1.08l-4.25 3.65a.75.75 0 01-1.04 0L5.21 8.27a.75.75 0 01.02-1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
              </div>
            </div>

            {agentSetKey && (
              <div className="min-w-0 sm:col-span-2 xl:col-span-1">
                <label className="mb-1 block text-xs font-semibold uppercase text-slate-500">
                  Agent
                </label>
                <div className="relative">
                  <select
                    value={selectedAgentName}
                    onChange={handleSelectedAgentChange}
                    className="w-full appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                  >
                    {selectedAgentConfigSet?.map((agent) => (
                      <option key={agent.name} value={agent.name}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-slate-500">
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M5.23 7.21a.75.75 0 011.06.02L10 10.44l3.71-3.21a.75.75 0 111.04 1.08l-4.25 3.65a.75.75 0 01-1.04 0L5.21 8.27a.75.75 0 01.02-1.06z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-2 sm:p-3 lg:flex-row">
        <Transcript
          userText={userText}
          setUserText={setUserText}
          onSendMessage={handleSendTextMessage}
          downloadRecording={downloadRecording}
          canDownloadRecording={false}
          canSend={sessionStatus === "CONNECTED"}
          sessionStatus={sessionStatus}
          isMicrophoneEnabled={isMicrophoneEnabled}
          micActivity={micMeter.micActivity}
          isAssistantSpeaking={isAssistantSpeaking}
          activeAgentName={selectedAgentName}
        />
        <Events isExpanded={isEventsPaneExpanded} />
      </div>

      <BottomToolbar
        sessionStatus={sessionStatus}
        onToggleConnection={onToggleConnection}
        isMicrophoneEnabled={isMicrophoneEnabled}
        setIsMicrophoneEnabled={setIsMicrophoneEnabled}
        isEventsPaneExpanded={isEventsPaneExpanded}
        setIsEventsPaneExpanded={setIsEventsPaneExpanded}
        isAudioPlaybackEnabled={isAudioPlaybackEnabled}
        setIsAudioPlaybackEnabled={setIsAudioPlaybackEnabled}
        areFillerSoundsEnabled={areFillerSoundsEnabled}
        setAreFillerSoundsEnabled={setAreFillerSoundsEnabled}
        codec={urlCodec}
        onCodecChange={handleCodecChange}
      />
      </div>
    </div>
  );
}

export default App;
