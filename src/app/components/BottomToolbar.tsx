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

  const handleTalkPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!e.isPrimary) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    handleTalkButtonDown();
  };

  const handleTalkPointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!e.isPrimary) return;
    e.preventDefault();
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    handleTalkButtonUp();
  };

  function getConnectionButtonLabel() {
    if (isConnected) return "Disconnect";
    if (isConnecting) return "Connecting...";
    return "Connect";
  }

  function getConnectionButtonClasses() {
    const baseClasses =
      "inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold text-white shadow-sm transition sm:w-36";
    const cursorClass = isConnecting ? "cursor-not-allowed" : "cursor-pointer";

    if (isConnected) {
      return `bg-rose-600 hover:bg-rose-700 ${cursorClass} ${baseClasses}`;
    }

    return `bg-slate-900 hover:bg-slate-800 ${cursorClass} ${baseClasses}`;
  }

  return (
    <div className="border-t border-slate-200 bg-white/95 px-3 py-3 backdrop-blur sm:px-4">
      <div className="mx-auto grid max-w-7xl gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-sm lg:grid-cols-[auto_1fr_auto] lg:items-center lg:p-4">
        <div className="grid grid-cols-2 gap-2 sm:flex sm:items-center">
          <button
            onClick={onToggleConnection}
            className={getConnectionButtonClasses()}
            disabled={isConnecting}
          >
            {isConnected ? <ExitIcon /> : <EnterIcon />}
            {getConnectionButtonLabel()}
          </button>

          <label className="inline-flex h-12 cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
            <input
              id="push-to-talk"
              type="checkbox"
              checked={isPTTActive}
              onChange={(e) => setIsPTTActive(e.target.checked)}
              disabled={!isConnected}
              className="h-4 w-4"
            />
            Push to talk
          </label>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm">
          <button
            onPointerDown={handleTalkPointerDown}
            onPointerUp={handleTalkPointerUp}
            onPointerCancel={handleTalkPointerUp}
            disabled={!isConnected || !isPTTActive}
            className={
              "group relative flex min-h-20 w-full touch-none items-center justify-center overflow-hidden rounded-xl px-5 py-4 text-center transition active:scale-[0.99] sm:min-h-16 " +
              (isConnected && isPTTActive
                ? isPTTUserSpeaking
                  ? "bg-emerald-600 text-white shadow-[0_0_0_4px_rgba(16,185,129,0.16)]"
                  : "bg-slate-900 text-white hover:bg-slate-800"
                : "cursor-not-allowed bg-slate-100 text-slate-400")
            }
          >
            <span
              className={
                "mr-3 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full " +
                (isPTTUserSpeaking ? "bg-white/20" : "bg-white/10")
              }
              aria-hidden="true"
            >
              <span
                className={
                  "h-3 w-3 rounded-full " +
                  (isPTTUserSpeaking ? "bg-white" : "bg-emerald-300")
                }
              />
            </span>
            <span className="min-w-0">
              <span className="block text-base font-semibold">
                {isPTTUserSpeaking ? "Listening..." : "Hold to talk"}
              </span>
              <span className="block text-xs opacity-75">
                {isConnected
                  ? isPTTActive
                    ? "Press and release when finished"
                    : "Turn on push to talk to use this"
                  : "Connect to start a call"}
              </span>
            </span>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:flex lg:items-center">
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
              "flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-3 text-sm shadow-sm transition " +
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

          <div className="col-span-2 flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 shadow-sm sm:col-span-1">
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
    </div>
  );
}

export default BottomToolbar;
