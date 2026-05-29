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
    deepgram_stt_model: str = Field(default="nova-3", alias="DEEPGRAM_STT_MODEL")
    deepgram_stt_alt_model: str = Field(default="flux-general-en", alias="DEEPGRAM_STT_ALT_MODEL")
    deepgram_endpointing_ms: int = Field(default=300, alias="DEEPGRAM_ENDPOINTING_MS")
    deepgram_utterance_end_ms: int = Field(default=1000, alias="DEEPGRAM_UTTERANCE_END_MS")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_stt_model: str = Field(default="scribe_v2_realtime", alias="ELEVENLABS_STT_MODEL")
    elevenlabs_stt_commit_strategy: str = Field(default="vad", alias="ELEVENLABS_STT_COMMIT_STRATEGY")
    elevenlabs_stt_commit_silence_ms: int = Field(default=250, alias="ELEVENLABS_STT_COMMIT_SILENCE_MS")
    elevenlabs_stt_vad_silence_threshold_secs: float = Field(
        default=0.9,
        alias="ELEVENLABS_STT_VAD_SILENCE_THRESHOLD_SECS",
    )
    elevenlabs_stt_vad_threshold: float = Field(default=0.35, alias="ELEVENLABS_STT_VAD_THRESHOLD")
    elevenlabs_stt_min_speech_duration_ms: int = Field(
        default=120,
        alias="ELEVENLABS_STT_MIN_SPEECH_DURATION_MS",
    )
    elevenlabs_stt_min_silence_duration_ms: int = Field(
        default=350,
        alias="ELEVENLABS_STT_MIN_SILENCE_DURATION_MS",
    )
    elevenlabs_stt_sample_rate: int = Field(default=16000, alias="ELEVENLABS_STT_SAMPLE_RATE")
    elevenlabs_tts_model: str = Field(default="eleven_flash_v2_5", alias="ELEVENLABS_TTS_MODEL")
    elevenlabs_tts_alt_model: str = Field(default="eleven_turbo_v2_5", alias="ELEVENLABS_TTS_ALT_MODEL")
    elevenlabs_voice_id: str = Field(default="JBFqnCBsd6RMkjVDRZzb", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_voice_callcenter: str = Field(
        default="SEWXl8lPSO01tdGbWECX",
        alias="ELEVENLABS_VOICE_CALLCENTER",
    )
    elevenlabs_voice_billing: str = Field(
        default="8AMr87HV4PA3NKEl5q4O",
        alias="ELEVENLABS_VOICE_BILLING",
    )
    elevenlabs_voice_technical_support: str = Field(
        default="OAQQSa5rh6bJe9HgSD5E",
        alias="ELEVENLABS_VOICE_TECHNICAL_SUPPORT",
    )
    elevenlabs_voice_retention: str = Field(
        default="LcfcDJNUP1GQjkzn1xUU",
        alias="ELEVENLABS_VOICE_RETENTION",
    )
    elevenlabs_voice_supervisor: str = Field(
        default="SDNKIYEpTz0h56jQX8rA",
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
    stress_lab_enabled: bool = Field(default=False, alias="STRESS_LAB_ENABLED")
    stress_lab_real_openai_tools_enabled: bool = Field(
        default=False,
        alias="STRESS_LAB_REAL_OPENAI_TOOLS_ENABLED",
    )
    stress_lab_results_path: str = Field(
        default="backend/.data/stress_lab_runs.json",
        alias="STRESS_LAB_RESULTS_PATH",
    )
    stress_lab_openai_model: str = Field(
        default="gpt-4.1",
        alias="STRESS_LAB_OPENAI_MODEL",
    )
    stress_lab_vector_store_id: str | None = Field(
        default=None,
        alias="STRESS_LAB_VECTOR_STORE_ID",
    )
    callcenter_rag_vector_store_id: str | None = Field(
        default=None,
        alias="CALLCENTER_RAG_VECTOR_STORE_ID",
    )
    mcp_gmail_oauth_token: str | None = Field(default=None, alias="MCP_GMAIL_OAUTH_TOKEN")
    mcp_gmail_require_approval: str = Field(default="always", alias="MCP_GMAIL_REQUIRE_APPROVAL")
    mcp_email_server_url: str | None = Field(default=None, alias="MCP_EMAIL_SERVER_URL")
    mcp_email_authorization: str | None = Field(default=None, alias="MCP_EMAIL_AUTHORIZATION")
    mcp_email_allowed_tools_raw: str = Field(
        default="send_email,send_message,create_draft",
        alias="MCP_EMAIL_ALLOWED_TOOLS",
    )
    mcp_email_require_approval: str = Field(default="always", alias="MCP_EMAIL_REQUIRE_APPROVAL")
    mcp_ticketing_server_url: str | None = Field(default=None, alias="MCP_TICKETING_SERVER_URL")
    mcp_ticketing_authorization: str | None = Field(default=None, alias="MCP_TICKETING_AUTHORIZATION")
    mcp_ticketing_allowed_tools_raw: str = Field(
        default="search_tickets,create_ticket,update_ticket,add_comment",
        alias="MCP_TICKETING_ALLOWED_TOOLS",
    )
    mcp_ticketing_require_approval: str = Field(default="always", alias="MCP_TICKETING_REQUIRE_APPROVAL")
    atenxion_bank_api_base_url: str = Field(
        default="https://api-qabank.atenxion.ai",
        alias="ATENXION_BANK_API_BASE_URL",
    )
    atenxion_bank_api_token: str | None = Field(default=None, alias="ATENXION_BANK_API_TOKEN")
    atenxion_bank_test_user_id: str = Field(
        default="6a0d6b143cac1525e1e4ce87",
        alias="ATENXION_BANK_TEST_USER_ID",
    )
    atenxion_bank_timeout_seconds: float = Field(
        default=10.0,
        alias="ATENXION_BANK_TIMEOUT_SECONDS",
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
