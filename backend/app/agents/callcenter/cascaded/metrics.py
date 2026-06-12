"""Tracks latency, rough usage, and cost estimates across STT, LLM, and TTS stages for each user turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


OPENAI_GPT41_MINI_INPUT_PER_1M = 0.40
OPENAI_GPT41_MINI_OUTPUT_PER_1M = 1.60
DEEPGRAM_PAYG_PER_MINUTE = {
    "flux-general-en": 0.0077,
    "flux-general-multi": 0.0078,
    "nova-3": 0.0077,
}
ELEVENLABS_FLASH_OR_TURBO_CREDITS_PER_CHAR = 0.5


def estimate_tokens(text: str) -> int:
    """Estimate token counts cheaply for turn-level cost telemetry."""
    return max(1, round(len(text) / 4))


@dataclass
class TurnMetrics:
    """Mutable per-turn telemetry object for cascaded latency, usage, and cost estimates."""
    architecture: str
    stt_provider: str
    stt_model: str
    llm_provider: str
    llm_model: str
    tts_provider: str
    tts_model: str
    tts_voice_id: str
    input_sample_rate: int
    output_sample_rate: int
    started_at: float = field(default_factory=monotonic)
    user_audio_bytes: int = 0
    user_text: str = ""
    assistant_text: str = ""
    openai_usage: dict[str, Any] | None = None
    stt_first_partial_ms: float | None = None
    stt_first_final_ms: float | None = None
    turn_detected_ms: float | None = None
    llm_first_token_ms: float | None = None
    first_sentence_ms: float | None = None
    tts_first_audio_ms: float | None = None
    total_turn_ms: float | None = None
    tts_characters: int = 0
    output_audio_bytes: int = 0

    def mark_ms(self) -> float:
        """Measure elapsed milliseconds since the turn started."""
        return round((monotonic() - self.started_at) * 1000, 3)

    def finish(self) -> None:
        """Record total turn latency when the assistant response finishes."""
        self.total_turn_ms = self.mark_ms()

    def usage(self) -> dict[str, Any]:
        """Convert collected byte, text, and TTS character counts into usage estimates."""
        input_audio_minutes = self.user_audio_bytes / 2 / self.input_sample_rate / 60
        output_audio_minutes = self.output_audio_bytes / 2 / self.output_sample_rate / 60
        usage = {
            "input_audio_minutes": round(input_audio_minutes, 6),
            "output_audio_minutes": round(output_audio_minutes, 6),
            "llm_input_tokens_est": estimate_tokens(self.user_text),
            "llm_output_tokens_est": estimate_tokens(self.assistant_text),
            "tts_characters": self.tts_characters,
        }
        if self.openai_usage is not None:
            usage["openai_usage"] = self.openai_usage
        return usage

    def cost_estimate(self) -> dict[str, Any]:
        """Estimate provider cost from current usage and configured static rates."""
        usage = self.usage()
        stt_rate = DEEPGRAM_PAYG_PER_MINUTE.get(self.stt_model, 0.0077)
        stt_cost = usage["input_audio_minutes"] * stt_rate
        openai_usage = self.openai_usage or {}
        llm_input_tokens = openai_usage.get("input_tokens", usage["llm_input_tokens_est"])
        llm_output_tokens = openai_usage.get("output_tokens", usage["llm_output_tokens_est"])
        llm_cost = (
            llm_input_tokens / 1_000_000 * OPENAI_GPT41_MINI_INPUT_PER_1M
            + llm_output_tokens / 1_000_000 * OPENAI_GPT41_MINI_OUTPUT_PER_1M
        )
        elevenlabs_credits = (
            usage["tts_characters"] * ELEVENLABS_FLASH_OR_TURBO_CREDITS_PER_CHAR
        )
        return {
            "currency": "USD",
            "stt_usd_est": round(stt_cost, 8),
            "llm_usd_est": round(llm_cost, 8),
            "llm_token_source": "openai_usage" if self.openai_usage else "estimate",
            "elevenlabs_credits_est": round(elevenlabs_credits, 3),
            "total_usd_est_excluding_elevenlabs_subscription": round(stt_cost + llm_cost, 8),
        }

    def as_event_payload(self) -> dict[str, Any]:
        """Package providers, latency, usage, and cost estimates for frontend telemetry events."""
        return {
            "architecture": self.architecture,
            "providers": {
                "stt": {"provider": self.stt_provider, "model": self.stt_model},
                "llm": {"provider": self.llm_provider, "model": self.llm_model},
                "tts": {
                    "provider": self.tts_provider,
                    "model": self.tts_model,
                    "voice_id": self.tts_voice_id,
                },
            },
            "latency_ms": {
                "stt_first_partial": self.stt_first_partial_ms,
                "stt_first_final": self.stt_first_final_ms,
                "turn_detected": self.turn_detected_ms,
                "llm_first_token": self.llm_first_token_ms,
                "first_sentence": self.first_sentence_ms,
                "tts_first_audio": self.tts_first_audio_ms,
                "total_turn": self.total_turn_ms,
            },
            "usage": self.usage(),
            "cost_estimate": self.cost_estimate(),
        }

