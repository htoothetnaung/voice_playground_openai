"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useEvent } from "../contexts/EventContext";
import { useTranscript } from "../contexts/TranscriptContext";
import { SessionStatus } from "../types";

const PCM_SAMPLE_RATE = 24000;
const AUDIO_START_LOOKAHEAD_SECONDS = 0.06;
const TRANSFER_AUDIO_SETTLE_MS = 120;
const BACKEND_REALTIME_PATH = "/api/v1/callcenter/realtime/ws";
const MIC_SAMPLE_BUCKETS = 28;
const MIC_METER_UPDATE_MS = 80;

export type MicActivity = "muted" | "quiet" | "noise" | "speech";

export type MicMeterState = {
  micLevel: number;
  micSamples: number[];
  micActivity: MicActivity;
};

type QueuedAudio = {
  data: string;
  agentName?: string;
};

export interface BackendRealtimeSessionCallbacks {
  onConnectionChange?: (status: SessionStatus) => void;
  onAgentHandoff?: (agentName: string) => void;
  onAgentToolStart?: (toolName: string) => void;
  onAgentToolEnd?: (toolName: string) => void;
  onTransferAudioStart?: (agentName?: string, durationMs?: number) => void;
  onTransferAudioEnd?: (agentName?: string) => void;
  onAssistantSpeechStart?: (agentName?: string) => void;
  onAssistantSpeechEnd?: () => void;
}

export interface BackendConnectOptions {
  agentName?: string;
  architecture?: string;
}

function getBackendWsUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL?.trim();
  if (explicit) {
    const normalized = explicit.replace(/\/+$/, "");
    if (
      typeof window !== "undefined" &&
      window.location.protocol === "https:" &&
      normalized.startsWith("ws://") &&
      !normalized.startsWith("ws://127.0.0.1") &&
      !normalized.startsWith("ws://localhost")
    ) {
      return `wss://${normalized.slice("ws://".length)}`;
    }
    return normalized;
  }

  const proxyBase = process.env.NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL?.trim();
  if (proxyBase) {
    const normalized = proxyBase.replace(/\/+$/, "");
    if (normalized.startsWith("https://")) {
      return `wss://${normalized.slice("https://".length)}${BACKEND_REALTIME_PATH}`;
    }
    if (normalized.startsWith("http://")) {
      return `ws://${normalized.slice("http://".length)}${BACKEND_REALTIME_PATH}`;
    }
  }

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${BACKEND_REALTIME_PATH}`;
  }

  return `ws://127.0.0.1:8000${BACKEND_REALTIME_PATH}`;
}

function maybeParseJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function extractMessageText(content: any[] = []): string {
  if (!Array.isArray(content)) return "";
  return content
    .map((entry) => {
      if (!entry || typeof entry !== "object") return "";
      if (entry.type === "input_text") return entry.text ?? "";
      if (entry.type === "text") return entry.text ?? "";
      if (entry.type === "audio") return entry.transcript ?? "";
      if (entry.type === "output_text") return entry.text ?? "";
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

function decodeBase64ToInt16(base64: string): Int16Array {
  const binary = window.atob(base64);
  const evenByteLength = binary.length - (binary.length % 2);
  const buffer = new ArrayBuffer(evenByteLength);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < evenByteLength; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(buffer);
}

function int16ToAudioBuffer(
  context: AudioContext,
  samples: Int16Array,
): AudioBuffer {
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    float32[i] = samples[i] / 32768;
  }
  const audioBuffer = context.createBuffer(1, float32.length, PCM_SAMPLE_RATE);
  audioBuffer.copyToChannel(float32, 0);
  return audioBuffer;
}

function float32ToInt16Bytes(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

function resampleLinear(
  input: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number,
): Float32Array {
  if (inputSampleRate === outputSampleRate) {
    return input;
  }

  const outputLength = Math.max(
    1,
    Math.round((input.length * outputSampleRate) / inputSampleRate),
  );
  const output = new Float32Array(outputLength);
  const ratio = inputSampleRate / outputSampleRate;

  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = i * ratio;
    const lowerIndex = Math.floor(sourceIndex);
    const upperIndex = Math.min(lowerIndex + 1, input.length - 1);
    const weight = sourceIndex - lowerIndex;
    output[i] = input[lowerIndex] * (1 - weight) + input[upperIndex] * weight;
  }

  return output;
}

export function useBackendRealtimeSession(
  callbacks: BackendRealtimeSessionCallbacks = {},
) {
  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const [status, setStatus] = useState<SessionStatus>("DISCONNECTED");
  const playbackEnabledRef = useRef(true);
  const microphoneEnabledRef = useRef(true);
  const manualPttModeRef = useRef(false);
  const pttSpeakingRef = useRef(false);
  const activeOutputSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const audioQueueRef = useRef<QueuedAudio[]>([]);
  const isProcessingAudioQueueRef = useRef(false);
  const nextPlaybackTimeRef = useRef(0);
  const playbackGenerationRef = useRef(0);
  const transferGateActiveRef = useRef(false);
  const transferGateTimerRef = useRef<number | null>(null);
  const pendingTransferDurationMsRef = useRef<number | null>(null);
  const outputAudioContextRef = useRef<AudioContext | null>(null);
  const inputAudioContextRef = useRef<AudioContext | null>(null);
  const microphoneStreamRef = useRef<MediaStream | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const inputSilenceGainRef = useRef<GainNode | null>(null);
  const hasBufferedAudioRef = useRef(false);
  const micFramesSentRef = useRef(0);
  const lastMicMeterUpdateRef = useRef(0);
  const callbacksRef = useRef<BackendRealtimeSessionCallbacks>(callbacks);
  const [micMeter, setMicMeter] = useState<MicMeterState>({
    micLevel: 0,
    micSamples: Array.from({ length: MIC_SAMPLE_BUCKETS }, () => 0),
    micActivity: "muted",
  });

  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const { logClientEvent, logServerEvent } = useEvent();
  const {
    addTranscriptBreadcrumb,
    addTranscriptMessage,
    updateTranscriptItem,
    updateTranscriptMessage,
  } = useTranscript();

  const updateStatus = useCallback(
    (nextStatus: SessionStatus) => {
      setStatus((currentStatus) =>
        currentStatus === nextStatus ? currentStatus : nextStatus,
      );
      callbacksRef.current.onConnectionChange?.(nextStatus);
      logClientEvent({}, nextStatus);
    },
    [logClientEvent],
  );

  const stopPlayback = useCallback(() => {
    playbackGenerationRef.current += 1;
    audioQueueRef.current = [];
    transferGateActiveRef.current = false;
    pendingTransferDurationMsRef.current = null;
    if (transferGateTimerRef.current !== null) {
      window.clearTimeout(transferGateTimerRef.current);
      transferGateTimerRef.current = null;
    }
    activeOutputSourcesRef.current.forEach((source) => {
      try {
        source.stop();
      } catch {
        // ignore stale source stop errors
      }
    });
    activeOutputSourcesRef.current = [];
    nextPlaybackTimeRef.current = 0;
    callbacksRef.current.onAssistantSpeechEnd?.();
  }, []);

  const ensureOutputAudioContext = useCallback(async () => {
    if (!outputAudioContextRef.current) {
      outputAudioContextRef.current = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
    }
    if (outputAudioContextRef.current.state === "suspended") {
      await outputAudioContextRef.current.resume();
    }
    return outputAudioContextRef.current;
  }, []);

  const startTransferGateTimer = useCallback(
    (durationMs: number) => {
      if (transferGateTimerRef.current !== null) return;
      transferGateTimerRef.current = window.setTimeout(() => {
        transferGateTimerRef.current = null;
        transferGateActiveRef.current = false;
        pendingTransferDurationMsRef.current = null;
        void processAudioQueue();
      }, durationMs + TRANSFER_AUDIO_SETTLE_MS);
    },
    [],
  );

  const maybeStartTransferGateTimer = useCallback(() => {
    const durationMs = pendingTransferDurationMsRef.current;
    if (!transferGateActiveRef.current || durationMs == null) return;
    if (activeOutputSourcesRef.current.length > 0) return;
    startTransferGateTimer(durationMs);
  }, [startTransferGateTimer]);

  const processAudioQueue = useCallback(async () => {
    if (transferGateActiveRef.current) {
      maybeStartTransferGateTimer();
      return;
    }
    if (isProcessingAudioQueueRef.current) return;
    isProcessingAudioQueueRef.current = true;
    const generation = playbackGenerationRef.current;

    try {
      while (
        audioQueueRef.current.length > 0 &&
        generation === playbackGenerationRef.current
      ) {
        const item = audioQueueRef.current.shift();
        if (!item) continue;

        callbacksRef.current.onAssistantSpeechStart?.(item.agentName);
        if (!playbackEnabledRef.current) continue;

        const audioContext = await ensureOutputAudioContext();
        if (generation !== playbackGenerationRef.current) break;

        const int16 = decodeBase64ToInt16(item.data);
        const audioBuffer = int16ToAudioBuffer(audioContext, int16);
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);

        const startAt = Math.max(
          audioContext.currentTime + AUDIO_START_LOOKAHEAD_SECONDS,
          nextPlaybackTimeRef.current,
        );
        source.start(startAt);
        nextPlaybackTimeRef.current = startAt + audioBuffer.duration;

        source.onended = () => {
          activeOutputSourcesRef.current = activeOutputSourcesRef.current.filter(
            (currentSource) => currentSource !== source,
          );
          if (activeOutputSourcesRef.current.length === 0) {
            callbacksRef.current.onAssistantSpeechEnd?.();
            maybeStartTransferGateTimer();
          }
        };

        activeOutputSourcesRef.current.push(source);
      }
    } finally {
      isProcessingAudioQueueRef.current = false;
      if (audioQueueRef.current.length > 0) {
        void processAudioQueue();
      }
    }
  }, [ensureOutputAudioContext, maybeStartTransferGateTimer]);

  const handleHistoryItem = useCallback(
    (item: any) => {
      if (!item || item.type !== "message") return;

      const itemId = item.itemId ?? item.item_id ?? item.id;
      const role = item.role;
      if (!itemId || (role !== "user" && role !== "assistant")) return;

      const text = extractMessageText(item.content ?? []);
      addTranscriptMessage(itemId, role, text || (role === "user" ? "[Transcribing...]" : ""));
      if (text) {
        updateTranscriptMessage(itemId, text, false);
        updateTranscriptItem(itemId, { status: "DONE" });
      }
    },
    [addTranscriptMessage, updateTranscriptItem, updateTranscriptMessage],
  );

  const handleHistoryUpdate = useCallback(
    (history: any[]) => {
      if (!Array.isArray(history)) return;
      history.forEach((item) => {
        if (!item || item.type !== "message") return;
        const itemId = item.itemId ?? item.item_id ?? item.id;
        if (!itemId) return;
        const text = extractMessageText(item.content ?? []);
        if (text) {
          updateTranscriptMessage(itemId, text, false);
          updateTranscriptItem(itemId, { status: "DONE" });
        }
      });
    },
    [updateTranscriptItem, updateTranscriptMessage],
  );

  const handleServerEvent = useCallback(
    async (event: any) => {
      logServerEvent(event);

      switch (event.type) {
        case "session_ready":
          sessionIdRef.current =
            typeof event.session_id === "string" ? event.session_id : null;
          addTranscriptBreadcrumb(`Python runtime connected: ${event.agent_name}`, {
            sessionId: event.session_id,
            traceId: event.trace_id,
            architecture: event.architecture,
            _breadcrumbType: "session",
          });
          break;
        case "architecture_selected":
          addTranscriptBreadcrumb(`Architecture: ${event.architecture}`, {
            sttModel: event.stt_model,
            llmModel: event.llm_model,
            ttsModel: event.tts_model,
            _breadcrumbType: "session",
          });
          break;
        case "stt_partial":
          addTranscriptBreadcrumb("STT partial transcript", {
            text: event.text,
            _breadcrumbType: "session",
          });
          break;
        case "stt_stream_ready":
          addTranscriptBreadcrumb("Deepgram STT stream ready", {
            sttModel: event.stt_model,
            _breadcrumbType: "session",
          });
          break;
        case "stt_final":
          addTranscriptBreadcrumb("STT final transcript", {
            text: event.text,
            isFinal: event.is_final,
            speechFinal: event.speech_final,
            _breadcrumbType: "session",
          });
          break;
        case "stt_audio_received":
          addTranscriptBreadcrumb("Microphone audio reached STT", {
            bytes: event.bytes,
            sttModel: event.stt_model,
            _breadcrumbType: "session",
          });
          break;
        case "turn_detected":
          addTranscriptBreadcrumb("User turn detected", {
            text: event.text,
            _breadcrumbType: "session",
          });
          break;
        case "metrics_update":
          addTranscriptBreadcrumb("Voice metrics", {
            latencyMs: event.latency_ms,
            usage: event.usage,
            providers: event.providers,
            _breadcrumbType: "session",
          });
          break;
        case "cost_estimate":
          addTranscriptBreadcrumb("Cost estimate", {
            ...event,
            _breadcrumbType: "session",
          });
          break;
        case "ticket_created":
          addTranscriptBreadcrumb(
            `Ticket created: ${event.ticket?.title ?? "Admin review"}`,
            {
              ticketId: event.ticket?.ticket_id,
              kind: event.ticket?.kind,
              priority: event.ticket?.priority,
              status: event.ticket?.status,
              summary: event.ticket?.summary,
              _breadcrumbType: "ticket",
            },
          );
          break;
        case "history_added":
          handleHistoryItem(event.item);
          break;
        case "history_updated":
          handleHistoryUpdate(event.history);
          break;
        case "handoff":
          callbacksRef.current.onAgentHandoff?.(event.to_agent);
          break;
        case "transfer_audio_start":
          transferGateActiveRef.current = true;
          pendingTransferDurationMsRef.current =
            typeof event.duration_ms === "number" ? event.duration_ms : 2500;
          callbacksRef.current.onTransferAudioStart?.(
            event.agent_name,
            event.duration_ms,
          );
          maybeStartTransferGateTimer();
          break;
        case "transfer_audio_end":
          callbacksRef.current.onTransferAudioEnd?.(event.agent_name);
          break;
        case "agent_speech_start":
          addTranscriptBreadcrumb(`Agent speech started: ${event.agent_name}`, {
            agentName: event.agent_name,
            _breadcrumbType: "audio",
          });
          break;
        case "agent_speech_end":
          addTranscriptBreadcrumb(`Agent speech ended: ${event.agent_name}`, {
            agentName: event.agent_name,
            _breadcrumbType: "audio",
          });
          break;
        case "tts_error":
          addTranscriptBreadcrumb(`TTS audio skipped: ${event.agent_name}`, {
            agentName: event.agent_name,
            error: event.error,
            _breadcrumbType: "audio",
          });
          callbacksRef.current.onAssistantSpeechEnd?.();
          break;
        case "tool_start":
          addTranscriptBreadcrumb(`function call: ${event.tool_name}`, {
            arguments: maybeParseJson(event.arguments),
            agentName: event.agent_name,
            _breadcrumbType: "tool_call",
          });
          callbacksRef.current.onAgentToolStart?.(event.tool_name);
          break;
        case "tool_end":
          addTranscriptBreadcrumb(`function call result: ${event.tool_name}`, {
            result: maybeParseJson(event.output),
            agentName: event.agent_name,
            _breadcrumbType: "tool_result",
          });
          callbacksRef.current.onAgentToolEnd?.(event.tool_name);
          break;
        case "audio": {
          if (typeof event.data === "string") {
            audioQueueRef.current.push({
              data: event.data,
              agentName: event.agent_name,
            });
            void processAudioQueue();
          }
          break;
        }
        case "audio_end":
          callbacksRef.current.onAssistantSpeechEnd?.();
          break;
        case "audio_interrupted":
          stopPlayback();
          break;
        case "guardrail_tripped":
          addTranscriptBreadcrumb("Output Guardrail Active", {
            details: event.guardrail_results,
            _breadcrumbType: "guardrail",
          });
          break;
        case "error":
          addTranscriptBreadcrumb("Python runtime error", {
            error: event.error,
            _breadcrumbType: "guardrail",
          });
          break;
        default:
          break;
      }
    },
    [
      addTranscriptBreadcrumb,
      handleHistoryItem,
      handleHistoryUpdate,
      logServerEvent,
      maybeStartTransferGateTimer,
      processAudioQueue,
      stopPlayback,
    ],
  );

  const updateMicMeter = useCallback((input: Float32Array) => {
    const now = window.performance.now();
    if (now - lastMicMeterUpdateRef.current < MIC_METER_UPDATE_MS) return;
    lastMicMeterUpdateRef.current = now;

    let sumSquares = 0;
    let peak = 0;
    for (let i = 0; i < input.length; i += 1) {
      const sample = Math.abs(input[i]);
      sumSquares += sample * sample;
      if (sample > peak) peak = sample;
    }

    const rms = Math.sqrt(sumSquares / Math.max(1, input.length));
    const normalizedLevel = microphoneEnabledRef.current
      ? Math.min(1, Math.max(peak * 1.4, Math.sqrt(rms) * 2.4))
      : 0;
    const micActivity: MicActivity = !microphoneEnabledRef.current
      ? "muted"
      : rms >= 0.055
        ? "speech"
        : rms >= 0.012
          ? "noise"
          : "quiet";

    setMicMeter((current) => ({
      micLevel: normalizedLevel,
      micActivity,
      micSamples: [...current.micSamples.slice(1), normalizedLevel],
    }));
  }, []);

  const ensureMicrophonePipeline = useCallback(async () => {
    if (microphoneStreamRef.current && processorNodeRef.current && inputAudioContextRef.current) {
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const audioContext = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
    const sourceNode = audioContext.createMediaStreamSource(stream);
    const processorNode = audioContext.createScriptProcessor(4096, 1, 1);

    processorNode.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      updateMicMeter(input);

      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      const shouldStreamAudio =
        microphoneEnabledRef.current &&
        (!manualPttModeRef.current || pttSpeakingRef.current);
      if (!shouldStreamAudio) return;

      const resampledInput = resampleLinear(
        input,
        event.inputBuffer.sampleRate,
        PCM_SAMPLE_RATE,
      );
      const pcmBuffer = float32ToInt16Bytes(resampledInput);
      if (pcmBuffer.byteLength === 0) return;
      hasBufferedAudioRef.current = true;
      micFramesSentRef.current += 1;
      ws.send(pcmBuffer);
    };

    const inputSilenceGain = audioContext.createGain();
    inputSilenceGain.gain.value = 0;
    sourceNode.connect(processorNode);
    processorNode.connect(inputSilenceGain);
    inputSilenceGain.connect(audioContext.destination);

    microphoneStreamRef.current = stream;
    inputAudioContextRef.current = audioContext;
    sourceNodeRef.current = sourceNode;
    processorNodeRef.current = processorNode;
    inputSilenceGainRef.current = inputSilenceGain;
  }, [updateMicMeter]);

  const resumeInputAudioContext = useCallback(() => {
    const audioContext = inputAudioContextRef.current;
    if (!audioContext || audioContext.state !== "suspended") return;
    audioContext.resume().catch(() => undefined);
  }, []);

  const cleanupMicrophonePipeline = useCallback(async () => {
    processorNodeRef.current?.disconnect();
    sourceNodeRef.current?.disconnect();
    inputSilenceGainRef.current?.disconnect();
    processorNodeRef.current = null;
    sourceNodeRef.current = null;
    inputSilenceGainRef.current = null;

    if (inputAudioContextRef.current) {
      await inputAudioContextRef.current.close();
      inputAudioContextRef.current = null;
    }

    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
  }, []);

  const connect = useCallback(
    async ({ agentName, architecture }: BackendConnectOptions) => {
      if (wsRef.current) return;

      updateStatus("CONNECTING");
      hasBufferedAudioRef.current = false;
      micFramesSentRef.current = 0;
      await ensureMicrophonePipeline();
      resumeInputAudioContext();

      const firstAgent = agentName ?? "callcenteragent";
      const params = new URLSearchParams({ agent_name: firstAgent });
      if (architecture) {
        params.set("architecture", architecture);
      }
      const url = `${getBackendWsUrl()}?${params.toString()}`;
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        updateStatus("CONNECTED");
        resumeInputAudioContext();
      };

      ws.onmessage = (message) => {
        if (typeof message.data !== "string") return;
        const payload = JSON.parse(message.data);
        void handleServerEvent(payload);
      };

      ws.onerror = () => {
        addTranscriptBreadcrumb("Backend realtime socket error", {
          url,
          readyState: ws.readyState,
          _breadcrumbType: "guardrail",
        });
      };

      ws.onclose = (event) => {
        if (status !== "DISCONNECTED") {
          addTranscriptBreadcrumb("Backend realtime socket closed", {
            url,
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean,
            _breadcrumbType: "guardrail",
          });
        }
        stopPlayback();
        wsRef.current = null;
        sessionIdRef.current = null;
        updateStatus("DISCONNECTED");
      };
    },
    [
      addTranscriptBreadcrumb,
      ensureMicrophonePipeline,
      handleServerEvent,
      resumeInputAudioContext,
      status,
      stopPlayback,
      updateStatus,
    ],
  );

  const disconnect = useCallback(() => {
    stopPlayback();
    pttSpeakingRef.current = false;
    manualPttModeRef.current = false;
    hasBufferedAudioRef.current = false;
    sessionIdRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    void cleanupMicrophonePipeline();
    setMicMeter({
      micLevel: 0,
      micSamples: Array.from({ length: MIC_SAMPLE_BUCKETS }, () => 0),
      micActivity: "muted",
    });
    updateStatus("DISCONNECTED");
  }, [cleanupMicrophonePipeline, stopPlayback, updateStatus]);

  const sendUserText = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      throw new Error("Backend realtime session not connected");
    }
    wsRef.current.send(JSON.stringify({ type: "user_text", text }));
  }, []);

  const sendEvent = useCallback((event: any) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const eventType = typeof event?.type === "string" ? event.type : "client_event";

    ws.send(
      JSON.stringify({
        type: "client_event",
        event: {
          type: eventType,
          session_id: sessionIdRef.current,
          payload: event,
        },
      }),
    );

    if (event?.type === "session.update") {
      const turnDetection = event?.session?.audio?.input?.turn_detection;
      manualPttModeRef.current = turnDetection == null;
      return;
    }

    if (event?.type === "input_audio_buffer.clear") {
      pttSpeakingRef.current = true;
      hasBufferedAudioRef.current = false;
      micFramesSentRef.current = 0;
      resumeInputAudioContext();
      return;
    }

    if (event?.type === "input_audio_buffer.commit") {
      pttSpeakingRef.current = false;
      if (!hasBufferedAudioRef.current) {
        return;
      }
      hasBufferedAudioRef.current = false;
      ws.send(JSON.stringify({ type: "audio_commit" }));
      return;
    }

    if (event?.type === "conversation.item.create") {
      const text = event?.item?.content?.find((entry: any) => entry.type === "input_text")?.text;
      if (typeof text === "string" && text.trim()) {
        ws.send(JSON.stringify({ type: "user_text", text }));
      }
      return;
    }
  }, [addTranscriptBreadcrumb, resumeInputAudioContext]);

  const interrupt = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    resumeInputAudioContext();
    stopPlayback();
    wsRef.current.send(JSON.stringify({ type: "interrupt" }));
  }, [resumeInputAudioContext, stopPlayback]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.addEventListener("pointerdown", resumeInputAudioContext);
    window.addEventListener("keydown", resumeInputAudioContext);
    return () => {
      window.removeEventListener("pointerdown", resumeInputAudioContext);
      window.removeEventListener("keydown", resumeInputAudioContext);
    };
  }, [resumeInputAudioContext]);

  const mute = useCallback((muted: boolean) => {
    playbackEnabledRef.current = !muted;
    if (muted) {
      stopPlayback();
    }
  }, [stopPlayback]);

  const setMicrophoneEnabled = useCallback((enabled: boolean) => {
    microphoneEnabledRef.current = enabled;
    if (enabled) {
      resumeInputAudioContext();
      return;
    }

    pttSpeakingRef.current = false;
    hasBufferedAudioRef.current = false;
    setMicMeter((current) => ({
      micLevel: 0,
      micSamples: current.micSamples.map(() => 0),
      micActivity: "muted",
    }));
  }, [resumeInputAudioContext]);

  useEffect(() => {
    const teardown = async () => {
      stopPlayback();
      pttSpeakingRef.current = false;
      manualPttModeRef.current = false;
      wsRef.current?.close();
      wsRef.current = null;
      sessionIdRef.current = null;
      await cleanupMicrophonePipeline();
      if (outputAudioContextRef.current) {
        await outputAudioContextRef.current.close();
        outputAudioContextRef.current = null;
      }
    };

    return () => {
      void teardown();
    };
  }, [cleanupMicrophonePipeline, stopPlayback]);

  return {
    status,
    connect,
    disconnect,
    sendUserText,
    sendEvent,
    mute,
    setMicrophoneEnabled,
    micMeter,
    interrupt,
  } as const;
}
