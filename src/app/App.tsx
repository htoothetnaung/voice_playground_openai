"use client";
import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { v4 as uuidv4 } from "uuid";

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
    searchParams.get("architecture") || "openai_native";
  const { addTranscriptMessage, addTranscriptBreadcrumb } = useTranscript();
  const { logClientEvent } = useEvent();
  const {
    playTransfer,
    stopToolWait,
    stopAll,
    setAssistantAudioActive,
  } = useFillerAudio();

  const [selectedAgentName, setSelectedAgentName] = useState<string>("");
  const [selectedAgentConfigSet, setSelectedAgentConfigSet] = useState<
    AgentOption[] | null
  >(null);
  const [sessionStatus, setSessionStatus] =
    useState<SessionStatus>("DISCONNECTED");
  const [isEventsPaneExpanded, setIsEventsPaneExpanded] =
    useState<boolean>(true);
  const [userText, setUserText] = useState<string>("");
  const [isPTTActive, setIsPTTActive] = useState<boolean>(false);
  const [isPTTUserSpeaking, setIsPTTUserSpeaking] = useState<boolean>(false);
  const [isAudioPlaybackEnabled, setIsAudioPlaybackEnabled] = useState<boolean>(
    () => {
      if (typeof window === "undefined") return true;
      const stored = localStorage.getItem("audioPlaybackEnabled");
      return stored ? stored === "true" : true;
    }
  );
  const handoffTriggeredRef = useRef(false);

  const { connect, disconnect, sendUserText, sendEvent, interrupt, mute } =
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
        playTransfer(durationMs ? durationMs + 750 : undefined);
      },
      onTransferAudioEnd: (agentName?: string) => {
        addTranscriptBreadcrumb("Filler audio: transfer window complete", {
          state: "waiting_for_agent_audio",
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
        setAssistantAudioActive(true);
      },
      onAssistantSpeechEnd: () => {
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

  useEffect(() => {
    if (sessionStatus === "CONNECTED") {
      updateSession();
    }
  }, [isPTTActive]);

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
    stopAll();
    disconnect();
    setSessionStatus("DISCONNECTED");
    setIsPTTUserSpeaking(false);
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
    const turnDetection = isPTTActive
      ? null
      : {
          type: "server_vad",
          threshold: 0.9,
          prefix_padding_ms: 300,
          silence_duration_ms: 500,
          create_response: true,
        };

    sendEvent({
      type: "session.update",
      session: {
        turn_detection: turnDetection,
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

  const handleTalkButtonDown = () => {
    if (sessionStatus !== "CONNECTED") return;
    interrupt();

    setIsPTTUserSpeaking(true);
    sendClientEvent({ type: "input_audio_buffer.clear" }, "clear PTT buffer");
  };

  const handleTalkButtonUp = () => {
    if (sessionStatus !== "CONNECTED" || !isPTTUserSpeaking) return;

    setIsPTTUserSpeaking(false);
    sendClientEvent({ type: "input_audio_buffer.commit" }, "commit PTT");
    sendClientEvent({ type: "response.create" }, "trigger response PTT");
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
    const storedPushToTalkUI = localStorage.getItem("pushToTalkUI");
    if (storedPushToTalkUI) {
      setIsPTTActive(storedPushToTalkUI === "true");
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
  }, []);

  useEffect(() => {
    localStorage.setItem("pushToTalkUI", isPTTActive.toString());
  }, [isPTTActive]);

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
    if (sessionStatus === "DISCONNECTED") {
      setAssistantAudioActive(false);
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
    <div className="relative flex h-screen flex-col bg-slate-100 text-base text-slate-800">
      <div className="border-b border-slate-200 bg-white/90 px-6 py-5 backdrop-blur">
        <div className="flex items-center justify-between gap-4">
          <div
            className="flex cursor-pointer items-center gap-3"
            onClick={() => window.location.reload()}
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 bg-slate-100">
              <Image
                src="/atenxion_logo.png"
                alt="Atenxion Logo"
                width={28}
                height={28}
              />
            </div>
            <div className="flex flex-col">
              <span className="text-lg font-semibold text-slate-900">
                Atenxion Call Center Lab
              </span>
              <span className="text-sm font-normal text-slate-500">
                Realtime handoffs, tool calls, guardrails, and call-floor audio cues
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
              Telecom support simulation
            </div>
            <label className="mr-2 flex items-center gap-1 text-sm font-medium text-slate-600">
              Architecture
            </label>
            <div className="relative inline-block">
              <select
                value={selectedArchitecture}
                onChange={handleArchitectureChange}
                className="appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none"
              >
                <option value="openai_native">OpenAI native realtime</option>
                <option value="cascaded_pipeline">Deepgram + GPT + ElevenLabs</option>
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
            <label className="mr-2 flex items-center gap-1 text-sm font-medium text-slate-600">
              Scenario
            </label>
            <div className="relative inline-block">
              <select
                value={agentSetKey}
                onChange={handleAgentChange}
                className="appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none"
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

            {agentSetKey && (
              <div className="flex items-center">
                <label className="mr-2 flex items-center gap-1 text-sm font-medium text-slate-600">
                  Agent
                </label>
                <div className="relative inline-block">
                  <select
                    value={selectedAgentName}
                    onChange={handleSelectedAgentChange}
                    className="appearance-none cursor-pointer rounded-xl border border-slate-300 bg-white px-3 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:outline-none"
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

      <div className="relative flex flex-1 gap-3 overflow-hidden p-3">
        <Transcript
          userText={userText}
          setUserText={setUserText}
          onSendMessage={handleSendTextMessage}
          downloadRecording={downloadRecording}
          canDownloadRecording={false}
          canSend={sessionStatus === "CONNECTED"}
        />
        <Events isExpanded={isEventsPaneExpanded} />
      </div>

      <BottomToolbar
        sessionStatus={sessionStatus}
        onToggleConnection={onToggleConnection}
        isPTTActive={isPTTActive}
        setIsPTTActive={setIsPTTActive}
        isPTTUserSpeaking={isPTTUserSpeaking}
        handleTalkButtonDown={handleTalkButtonDown}
        handleTalkButtonUp={handleTalkButtonUp}
        isEventsPaneExpanded={isEventsPaneExpanded}
        setIsEventsPaneExpanded={setIsEventsPaneExpanded}
        isAudioPlaybackEnabled={isAudioPlaybackEnabled}
        setIsAudioPlaybackEnabled={setIsAudioPlaybackEnabled}
        codec={urlCodec}
        onCodecChange={handleCodecChange}
      />
    </div>
  );
}

export default App;
