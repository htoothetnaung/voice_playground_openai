# Atenxion Call Center ADK Backend

This backend is a Google ADK v1 sibling implementation for the existing Atenxion `callcenteragent` workflow.

It keeps the same FastAPI route shape and frontend WebSocket protocol as `backend`, but the call-center LLM orchestration uses Google ADK instead of the OpenAI Agents SDK.

## Runtime Stack

- `FastAPI` for HTTP APIs and WebSocket serving
- `google-adk` for agent orchestration, tools, sessions, and transfers
- `DatabaseSessionService` with SQLite via `aiosqlite`
- Deepgram STT and ElevenLabs TTS for the cascaded voice path
- MongoDB when available for mock-data seeding and admin audit records

## Scope

The ADK backend intentionally supports the cascaded architecture only:

```text
Browser audio/text -> FastAPI WebSocket -> Deepgram -> Google ADK/Gemini -> ElevenLabs -> Browser audio/events
```

OpenAI native realtime is not implemented in `backend_adk`.

## Endpoints

- `GET /api/health`
- `GET /api/session`
- `POST /api/responses`
- `GET /api/v1/callcenter/scenario`
- `POST /api/v1/callcenter/run`
- `WS /api/v1/callcenter/realtime/ws`
- `POST /api/v1/callcenter/seed`
- `POST /api/v1/callcenter/sessions/{session_id}/events`
- `GET /api/v1/callcenter/admin/sessions`
- `GET /api/v1/callcenter/admin/sessions/{session_id}`
- stress-lab routes copied for compatibility

## Local Development

1. Configure `.env`:

```bash
GOOGLE_API_KEY=your_google_ai_studio_key
GOOGLE_ADK_MODEL=gemini-2.5-flash
ADK_SESSION_DB_PATH=backend_adk/.data/callcenter_sessions.db
BACKEND_ADK_PORT=8001
VOICE_PROVIDER=cascaded_pipeline

FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8001
NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8001
NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=ws://127.0.0.1:8001/api/v1/callcenter/realtime/ws
```

2. Install and run:

```bash
uv sync --project backend_adk
uv run --project backend_adk uvicorn app.main:app --app-dir backend_adk --host 127.0.0.1 --port 8001 --reload
```

3. Run tests:

```bash
uv run --project backend_adk pytest backend_adk/tests
```
