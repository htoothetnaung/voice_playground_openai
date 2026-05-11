"""Loads environment-driven configuration for OpenAI, Deepgram, ElevenLabs, CORS, models, sample rates, and session persistence."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central environment-backed configuration object used by API routes, voice providers, and agent runtimes."""
    _ROOT_DIR = Path(__file__).resolve().parents[3]
    _BACKEND_DIR = Path(__file__).resolve().parents[2]

    model_config = SettingsConfigDict(
        env_file=(
            str(_ROOT_DIR / ".env"),
            str(_BACKEND_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    backend_base_url: str = Field(default="http://127.0.0.1:8000", alias="BACKEND_BASE_URL")
    frontend_backend_base_url: str = Field(
        default="http://127.0.0.1:8000",
        alias="FRONTEND_BACKEND_BASE_URL",
    )
    allowed_origins_raw: str = Field(
        default="http://127.0.0.1:3000,http://localhost:3000",
        alias="ALLOWED_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    voice_provider: str = Field(default="openai_native", alias="VOICE_PROVIDER")
    realtime_model: str = Field(default="gpt-realtime-1.5", alias="OPENAI_REALTIME_MODEL")
    responses_model: str = Field(default="gpt-4.1", alias="OPENAI_RESPONSES_MODEL")
    cascaded_llm_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_CASCADED_LLM_MODEL")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    deepgram_stt_model: str = Field(default="flux-general-en", alias="DEEPGRAM_STT_MODEL")
    deepgram_stt_alt_model: str = Field(default="nova-3", alias="DEEPGRAM_STT_ALT_MODEL")
    deepgram_endpointing_ms: int = Field(default=300, alias="DEEPGRAM_ENDPOINTING_MS")
    deepgram_utterance_end_ms: int = Field(default=1000, alias="DEEPGRAM_UTTERANCE_END_MS")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_tts_model: str = Field(default="eleven_flash_v2_5", alias="ELEVENLABS_TTS_MODEL")
    elevenlabs_tts_alt_model: str = Field(default="eleven_turbo_v2_5", alias="ELEVENLABS_TTS_ALT_MODEL")
    elevenlabs_voice_id: str = Field(default="JBFqnCBsd6RMkjVDRZzb", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_voice_callcenter: str = Field(
        default="21m00Tcm4TlvDq8ikWAM",
        alias="ELEVENLABS_VOICE_CALLCENTER",
    )
    elevenlabs_voice_billing: str = Field(
        default="pNInz6obpgDQGcFmaJgB",
        alias="ELEVENLABS_VOICE_BILLING",
    )
    elevenlabs_voice_technical_support: str = Field(
        default="nPczCjzI2devNBz1zQrb",
        alias="ELEVENLABS_VOICE_TECHNICAL_SUPPORT",
    )
    elevenlabs_voice_retention: str = Field(
        default="LcfcDJNUP1GQjkzn1xUU",
        alias="ELEVENLABS_VOICE_RETENTION",
    )
    elevenlabs_voice_supervisor: str = Field(
        default="EXAVITQu4vr4xnSDxMaL",
        alias="ELEVENLABS_VOICE_SUPERVISOR",
    )
    elevenlabs_voice_human_escalation: str = Field(
        default="TxGEqnHWrfWFTfGW9XjX",
        alias="ELEVENLABS_VOICE_HUMAN_ESCALATION",
    )
    cascaded_input_sample_rate: int = Field(default=24000, alias="CASCADED_INPUT_SAMPLE_RATE")
    cascaded_output_sample_rate: int = Field(default=24000, alias="CASCADED_OUTPUT_SAMPLE_RATE")
    cascaded_provider_timeout_seconds: float = Field(
        default=30.0,
        alias="CASCADED_PROVIDER_TIMEOUT_SECONDS",
    )
    callcenter_session_db_path: str = Field(
        default="backend/.data/callcenter_sessions.db",
        alias="CALLCENTER_SESSION_DB_PATH",
    )
    mongodb_uri: str = Field(default="mongodb://127.0.0.1:27017", alias="MONGODB_URI")
    mongodb_db: str = Field(default="atenxion_callcenter", alias="MONGODB_DB")

    @property
    def allowed_origins(self) -> list[str]:
        """Parse the ALLOWED_ORIGINS setting into the list format expected by FastAPI CORS middleware."""
        stripped = self.allowed_origins_raw.strip()
        if stripped.startswith("["):
            import json

            parsed = json.loads(stripped)
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in stripped.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance so dependency injection and runtime code share one configuration snapshot."""
    return Settings()
