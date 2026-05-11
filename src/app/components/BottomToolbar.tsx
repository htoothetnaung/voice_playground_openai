import React from "react";

import { SessionStatus } from "@/app/types";

interface BottomToolbarProps {
  sessionStatus: SessionStatus;
  onToggleConnection: () => void;
  isPTTActive: boolean;
  setIsPTTActive: (val: boolean) => void;
  isPTTUserSpeaking: boolean;
  handleTalkButtonDown: () => void;
  handleTalkButtonUp: () => void;
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
  isPTTActive,
  setIsPTTActive,
  isPTTUserSpeaking,
  handleTalkButtonDown,
  handleTalkButtonUp,
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
      "h-full w-36 rounded-xl px-4 py-3 text-base font-medium text-white shadow-sm";
    const cursorClass = isConnecting ? "cursor-not-allowed" : "cursor-pointer";

    if (isConnected) {
      return `bg-rose-600 hover:bg-rose-700 ${cursorClass} ${baseClasses}`;
    }

    return `bg-slate-900 hover:bg-slate-800 ${cursorClass} ${baseClasses}`;
  }

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-6 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
        <button
          onClick={onToggleConnection}
          className={getConnectionButtonClasses()}
          disabled={isConnecting}
        >
          {getConnectionButtonLabel()}
        </button>

        <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 shadow-sm">
          <input
            id="push-to-talk"
            type="checkbox"
            checked={isPTTActive}
            onChange={(e) => setIsPTTActive(e.target.checked)}
            disabled={!isConnected}
            className="h-4 w-4"
          />
          <label htmlFor="push-to-talk" className="cursor-pointer text-sm text-slate-700">
            Push to talk
          </label>
          <button
            onMouseDown={handleTalkButtonDown}
            onMouseUp={handleTalkButtonUp}
            onTouchStart={handleTalkButtonDown}
            onTouchEnd={handleTalkButtonUp}
            disabled={!isPTTActive}
            className={`rounded-full px-4 py-1.5 text-sm ${
              isPTTActive
                ? isPTTUserSpeaking
                  ? "bg-slate-300 text-slate-900"
                  : "bg-slate-200 text-slate-900"
                : "bg-slate-100 text-slate-400"
            }`}
          >
            Talk
          </button>
        </div>

        <label className="flex cursor-pointer items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-700 shadow-sm">
          <input
            id="audio-playback"
            type="checkbox"
            checked={isAudioPlaybackEnabled}
            onChange={(e) => setIsAudioPlaybackEnabled(e.target.checked)}
            disabled={!isConnected}
            className="h-4 w-4"
          />
          Audio playback
        </label>

        <label className="flex cursor-pointer items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-700 shadow-sm">
          <input
            id="filler-sounds"
            type="checkbox"
            checked={areFillerSoundsEnabled}
            onChange={(e) => setAreFillerSoundsEnabled(e.target.checked)}
            className="h-4 w-4"
          />
          Filler sounds
        </label>

        <label className="flex cursor-pointer items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-700 shadow-sm">
          <input
            id="logs"
            type="checkbox"
            checked={isEventsPaneExpanded}
            onChange={(e) => setIsEventsPaneExpanded(e.target.checked)}
            className="h-4 w-4"
          />
          Logs
        </label>

        <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-700 shadow-sm">
          <span className="font-medium">Codec</span>
          <select
            id="codec-select"
            value={codec}
            onChange={handleCodecChange}
            className="cursor-pointer rounded-lg border border-slate-300 bg-white px-2 py-1 focus:outline-none"
          >
            <option value="opus">Opus (48 kHz)</option>
            <option value="pcmu">PCMU (8 kHz)</option>
            <option value="pcma">PCMA (8 kHz)</option>
          </select>
        </div>
      </div>
    </div>
  );
}

export default BottomToolbar;
