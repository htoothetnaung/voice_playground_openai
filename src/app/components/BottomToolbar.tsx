import React from "react";
import {
  ActivityLogIcon,
  EnterIcon,
  ExitIcon,
  MixerHorizontalIcon,
  SpeakerLoudIcon,
  SpeakerOffIcon,
} from "@radix-ui/react-icons";

import { SessionStatus } from "@/app/types";

interface BottomToolbarProps {
  sessionStatus: SessionStatus;
  onToggleConnection: () => void;
  isMicrophoneEnabled: boolean;
  setIsMicrophoneEnabled: (val: boolean) => void;
  isEventsPaneExpanded: boolean;
  setIsEventsPaneExpanded: (val: boolean) => void;
  isAudioPlaybackEnabled: boolean;
  setIsAudioPlaybackEnabled: (val: boolean) => void;
  areFillerSoundsEnabled: boolean;
  setAreFillerSoundsEnabled: (val: boolean) => void;
  codec: string;
  onCodecChange: (newCodec: string) => void;
}

function BottomToolbar({
  sessionStatus,
  onToggleConnection,
  isMicrophoneEnabled,
  setIsMicrophoneEnabled,
  isEventsPaneExpanded,
  setIsEventsPaneExpanded,
  isAudioPlaybackEnabled,
  setIsAudioPlaybackEnabled,
  areFillerSoundsEnabled,
  setAreFillerSoundsEnabled,
  codec,
  onCodecChange,
}: BottomToolbarProps) {
  const isConnected = sessionStatus === "CONNECTED";
  const isConnecting = sessionStatus === "CONNECTING";

  const handleCodecChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onCodecChange(e.target.value);
  };

  function getConnectionButtonLabel() {
    if (isConnected) return "Disconnect";
    if (isConnecting) return "Connecting...";
    return "Connect";
  }

  function getConnectionButtonClasses() {
    const baseClasses =
      "inline-flex h-12 min-w-32 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold text-white shadow-sm transition sm:w-36";
    const cursorClass = isConnecting ? "cursor-not-allowed" : "cursor-pointer";

    if (isConnected) {
      return `bg-rose-600 hover:bg-rose-700 ${cursorClass} ${baseClasses}`;
    }

    return `bg-slate-900 hover:bg-slate-800 ${cursorClass} ${baseClasses}`;
  }

  return (
    <div className="border-t border-slate-200 bg-white/95 px-3 py-3 backdrop-blur sm:px-4">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-sm sm:gap-3 xl:p-4">
        <button
          onClick={onToggleConnection}
          className={getConnectionButtonClasses()}
          disabled={isConnecting}
        >
          {isConnected ? <ExitIcon /> : <EnterIcon />}
          {getConnectionButtonLabel()}
        </button>

        <label
          className={
            "inline-flex h-12 cursor-pointer items-center justify-center gap-3 rounded-xl border px-3 text-sm font-semibold shadow-sm transition " +
            (isConnected && isMicrophoneEnabled
              ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
              : isConnected
                ? "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                : "cursor-not-allowed border-slate-200 bg-white text-slate-400")
          }
        >
          <input
            id="microphone-enabled"
            type="checkbox"
            checked={isMicrophoneEnabled}
            onChange={(e) => setIsMicrophoneEnabled(e.target.checked)}
            disabled={!isConnected}
            className="sr-only"
          />
          <span
            className={
              "relative h-5 w-9 rounded-full transition " +
              (isConnected && isMicrophoneEnabled
                ? "bg-emerald-500"
                : "bg-slate-300")
            }
            aria-hidden="true"
          >
            <span
              className={
                "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition " +
                (isMicrophoneEnabled ? "left-4" : "left-0.5")
              }
            />
          </span>
          Mic
        </label>

        <label
          className={
            "flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3 text-sm shadow-sm transition " +
            (isAudioPlaybackEnabled
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-slate-200 bg-white text-slate-600")
          }
        >
          <input
            id="audio-playback"
            type="checkbox"
            checked={isAudioPlaybackEnabled}
            onChange={(e) => setIsAudioPlaybackEnabled(e.target.checked)}
            disabled={!isConnected}
            className="sr-only"
          />
          {isAudioPlaybackEnabled ? <SpeakerLoudIcon /> : <SpeakerOffIcon />}
          Audio
        </label>

        <label
          className={
            "flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3 text-sm shadow-sm transition " +
            (areFillerSoundsEnabled
              ? "border-sky-200 bg-sky-50 text-sky-800"
              : "border-slate-200 bg-white text-slate-600")
          }
        >
          <input
            id="filler-sounds"
            type="checkbox"
            checked={areFillerSoundsEnabled}
            onChange={(e) => setAreFillerSoundsEnabled(e.target.checked)}
            className="h-4 w-4"
          />
          Filler
        </label>

        <label
          className={
            "hidden h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3 text-sm shadow-sm transition lg:flex " +
            (isEventsPaneExpanded
              ? "border-violet-200 bg-violet-50 text-violet-800"
              : "border-slate-200 bg-white text-slate-600")
          }
        >
          <input
            id="logs"
            type="checkbox"
            checked={isEventsPaneExpanded}
            onChange={(e) => setIsEventsPaneExpanded(e.target.checked)}
            className="sr-only"
          />
          <ActivityLogIcon />
          Logs
        </label>

        <div className="flex h-11 min-w-28 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 shadow-sm">
          <MixerHorizontalIcon className="flex-shrink-0" />
          <select
            id="codec-select"
            value={codec}
            onChange={handleCodecChange}
            className="min-w-0 flex-1 cursor-pointer bg-transparent text-sm focus:outline-none"
          >
            <option value="opus">Opus</option>
            <option value="pcmu">PCMU</option>
            <option value="pcma">PCMA</option>
          </select>
        </div>
      </div>
    </div>
  );
}

export default BottomToolbar;
