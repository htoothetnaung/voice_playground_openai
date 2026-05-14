"use client";

import { useCallback, useEffect, useRef } from "react";

const TRANSFER_AUDIO_SOURCES = [
  "/filler_sounds/realistic_phone_ringing.wav",
  "/filler_sounds/phone_transfer_ringing.mp3",
];

export function useFillerAudio(enabled: boolean = true) {
  const transferAudioRef = useRef<HTMLAudioElement | null>(null);
  const transferAudioSourceIndexRef = useRef(0);
  const transferStopTimerRef = useRef<number | null>(null);
  const pendingTransferDurationMsRef = useRef<number | undefined>(undefined);
  const pendingModeRef = useRef<"transfer" | null>(null);
  const assistantAudioActiveRef = useRef(false);
  const enabledRef = useRef(enabled);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const createTransferAudio = (sourceIndex: number): HTMLAudioElement => {
      const audio = new Audio(TRANSFER_AUDIO_SOURCES[sourceIndex]);
      audio.loop = true;
      audio.preload = "auto";
      audio.volume = 0.18;
      audio.addEventListener("error", () => {
        const nextSourceIndex = sourceIndex + 1;
        if (nextSourceIndex >= TRANSFER_AUDIO_SOURCES.length) return;
        transferAudioSourceIndexRef.current = nextSourceIndex;
        transferAudioRef.current?.pause();
        transferAudioRef.current = createTransferAudio(nextSourceIndex);
      });
      return audio;
    };

    transferAudioRef.current = createTransferAudio(transferAudioSourceIndexRef.current);
    transferAudioRef.current.load();

    return () => {
      if (transferStopTimerRef.current !== null) {
        window.clearTimeout(transferStopTimerRef.current);
      }
      transferAudioRef.current?.pause();
      transferAudioRef.current = null;
    };
  }, []);

  const stopAll = useCallback((clearPending: boolean = true) => {
    if (clearPending) {
      pendingModeRef.current = null;
      pendingTransferDurationMsRef.current = undefined;
    }
    if (transferStopTimerRef.current !== null) {
      window.clearTimeout(transferStopTimerRef.current);
      transferStopTimerRef.current = null;
    }

    if (transferAudioRef.current) {
      transferAudioRef.current.pause();
      transferAudioRef.current.currentTime = 0;
    }
  }, []);

  useEffect(() => {
    enabledRef.current = enabled;
    if (!enabled) {
      stopAll();
    }
  }, [enabled, stopAll]);

  const stopTransfer = useCallback(() => {
    if (pendingModeRef.current === "transfer") {
      pendingModeRef.current = null;
    }
    if (transferStopTimerRef.current !== null) {
      window.clearTimeout(transferStopTimerRef.current);
      transferStopTimerRef.current = null;
    }
    if (transferAudioRef.current) {
      transferAudioRef.current.pause();
      transferAudioRef.current.currentTime = 0;
    }
  }, []);

  const startTransferAudio = useCallback((maxDurationMs: number = 3500) => {
    if (!enabledRef.current) return;
    stopAll(false);
    const audio = transferAudioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    audio.load();
    audio.play().catch(() => undefined);
    if (typeof window !== "undefined") {
      transferStopTimerRef.current = window.setTimeout(() => {
        stopTransfer();
      }, maxDurationMs);
    }
  }, [stopAll, stopTransfer]);

  const flushPendingAudio = useCallback(() => {
    if (assistantAudioActiveRef.current) return;

    const pendingMode = pendingModeRef.current;
    const pendingTransferDurationMs = pendingTransferDurationMsRef.current;
    pendingModeRef.current = null;
    pendingTransferDurationMsRef.current = undefined;

    if (pendingMode === "transfer") {
      startTransferAudio(pendingTransferDurationMs);
    }
  }, [startTransferAudio]);

  const playTransfer = useCallback((maxDurationMs?: number) => {
    if (!enabledRef.current) return;
    if (assistantAudioActiveRef.current) {
      pendingModeRef.current = "transfer";
      pendingTransferDurationMsRef.current = maxDurationMs;
      return;
    }
    pendingModeRef.current = null;
    pendingTransferDurationMsRef.current = undefined;
    startTransferAudio(maxDurationMs);
  }, [startTransferAudio]);

  const playToolWait = useCallback(() => {
    pendingModeRef.current = null;
  }, []);

  const stopToolWait = useCallback(() => {}, []);

  const setAssistantAudioActive = useCallback(
    (isActive: boolean) => {
      assistantAudioActiveRef.current = isActive;
      if (isActive) {
        stopTransfer();
        return;
      }

      if (typeof window !== "undefined" && pendingModeRef.current) {
        window.setTimeout(() => {
          flushPendingAudio();
        }, 250);
      }
    },
    [flushPendingAudio, stopTransfer]
  );

  return {
    playTransfer,
    stopTransfer,
    playToolWait,
    stopToolWait,
    stopAll,
    setAssistantAudioActive,
  } as const;
}
