export type SpeechGateMode = "balanced";

export type SpeechActivityGateConfig = {
  speechGateEnabled: boolean;
  speechGateMode: SpeechGateMode;
  speechOpenMs: number;
  speechCloseMs: number;
  speechPreRollMs: number;
  speechMinRms: number;
  speechNoiseMultiplier: number;
};

export type SpeechFrameFeatures = {
  rms: number;
  peak: number;
  durationMs: number;
};

export type SpeechGateFrame = {
  audio: ArrayBuffer;
  features: SpeechFrameFeatures;
};

export type SpeechGateResult = {
  framesToSend: ArrayBuffer[];
  opened: boolean;
  closed: boolean;
  suppressed: boolean;
  isOpen: boolean;
  noiseFloor: number;
  speechThreshold: number;
};

export const BALANCED_SPEECH_GATE_CONFIG: SpeechActivityGateConfig = {
  speechGateEnabled: true,
  speechGateMode: "balanced",
  speechOpenMs: 320,
  speechCloseMs: 600,
  speechPreRollMs: 300,
  speechMinRms: 0.055,
  speechNoiseMultiplier: 3,
};

const INITIAL_NOISE_FLOOR = 0.008;
const NOISE_FLOOR_ALPHA = 0.08;

export function analyzeSpeechFrame(
  samples: Float32Array,
  durationMs: number,
): SpeechFrameFeatures {
  let sumSquares = 0;
  let peak = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.abs(samples[i]);
    sumSquares += sample * sample;
    if (sample > peak) peak = sample;
  }

  return {
    rms: Math.sqrt(sumSquares / Math.max(1, samples.length)),
    peak,
    durationMs,
  };
}

export class SpeechActivityGate {
  private readonly config: SpeechActivityGateConfig;
  private isOpenValue = false;
  private speechMs = 0;
  private silenceMs = 0;
  private noiseFloorValue = INITIAL_NOISE_FLOOR;
  private preRoll: SpeechGateFrame[] = [];

  constructor(config: Partial<SpeechActivityGateConfig> = {}) {
    this.config = { ...BALANCED_SPEECH_GATE_CONFIG, ...config };
  }

  get isOpen(): boolean {
    return this.isOpenValue;
  }

  reset(): void {
    this.isOpenValue = false;
    this.speechMs = 0;
    this.silenceMs = 0;
    this.noiseFloorValue = INITIAL_NOISE_FLOOR;
    this.preRoll = [];
  }

  processFrame(frame: SpeechGateFrame): SpeechGateResult {
    if (!this.config.speechGateEnabled) {
      return this.result([frame.audio], false, false, false);
    }

    const threshold = this.currentSpeechThreshold();
    const speechLike = this.isSpeechLike(frame.features, threshold);
    let opened = false;
    let closed = false;
    let suppressed = false;
    let framesToSend: ArrayBuffer[] = [];

    this.rememberPreRoll(frame);

    if (this.isOpenValue) {
      if (speechLike) {
        this.silenceMs = 0;
      } else {
        this.silenceMs += frame.features.durationMs;
      }

      if (this.silenceMs >= this.config.speechCloseMs) {
        this.isOpenValue = false;
        this.speechMs = 0;
        this.silenceMs = 0;
        closed = true;
        this.updateNoiseFloor(frame.features.rms);
      } else {
        framesToSend = [frame.audio];
      }

      return this.result(framesToSend, opened, closed, false);
    }

    if (speechLike) {
      this.speechMs += frame.features.durationMs;
      if (this.speechMs >= this.config.speechOpenMs) {
        this.isOpenValue = true;
        this.silenceMs = 0;
        opened = true;
        framesToSend = this.preRoll.map((entry) => entry.audio);
      } else {
        suppressed = true;
      }
    } else {
      this.speechMs = 0;
      this.updateNoiseFloor(frame.features.rms);
      suppressed = frame.features.rms > this.noiseFloorValue * 1.35;
    }

    return this.result(framesToSend, opened, closed, suppressed);
  }

  private currentSpeechThreshold(): number {
    return Math.max(
      this.config.speechMinRms,
      this.noiseFloorValue * this.config.speechNoiseMultiplier,
    );
  }

  private isSpeechLike(features: SpeechFrameFeatures, threshold: number): boolean {
    return features.rms >= threshold && features.peak >= threshold * 1.6;
  }

  private rememberPreRoll(frame: SpeechGateFrame): void {
    this.preRoll.push(frame);
    let totalMs = 0;
    for (let i = this.preRoll.length - 1; i >= 0; i -= 1) {
      totalMs += this.preRoll[i].features.durationMs;
      if (totalMs > this.config.speechPreRollMs) {
        this.preRoll = this.preRoll.slice(i + 1);
        return;
      }
    }
  }

  private updateNoiseFloor(rms: number): void {
    const cappedRms = Math.min(rms, this.config.speechMinRms * 0.8);
    this.noiseFloorValue =
      this.noiseFloorValue * (1 - NOISE_FLOOR_ALPHA) + cappedRms * NOISE_FLOOR_ALPHA;
  }

  private result(
    framesToSend: ArrayBuffer[],
    opened: boolean,
    closed: boolean,
    suppressed: boolean,
  ): SpeechGateResult {
    return {
      framesToSend,
      opened,
      closed,
      suppressed,
      isOpen: this.isOpenValue,
      noiseFloor: this.noiseFloorValue,
      speechThreshold: this.currentSpeechThreshold(),
    };
  }
}
