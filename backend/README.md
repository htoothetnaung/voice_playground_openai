# Atenxion Call Center Backend

This backend is the Python migration target for the `callcenteragent` workflow.

It uses:

- `FastAPI` for HTTP APIs
- `openai-agents-python` for agent orchestration
- a provider gateway abstraction so OpenAI-native voice can be the first implementation

## Planned responsibilities

- Create realtime sessions for the active voice provider
- Proxy or normalize Responses API usage needed by the frontend
- Own the `callcenteragent` graph, prompts, tools, and mock data
- Expose backend-native execution endpoints for correctness, latency, and cost benchmarking

## Current scope

This migration only targets the Atenxion `callcenteragent` scenario. The existing frontend UI stays in
place, while the server-side responsibilities move into FastAPI and `openai-agents-python`.

Current endpoints:

- `GET /api/health`
- `GET /api/session`
- `POST /api/responses`
- `GET /api/v1/callcenter/scenario`
- `POST /api/v1/callcenter/run`
- `WS /api/v1/callcenter/realtime/ws`

## Local development

1. Copy `.env.sample` to `.env` and set `OPENAI_API_KEY`.
2. Install backend dependencies with `uv sync --project backend`.
3. Start the backend:

```bash
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

4. In a second terminal, start the frontend:

```bash
pnpm dev
```

5. Keep these in `.env` so the frontend can reach FastAPI:

```bash
FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=ws://127.0.0.1:8000/api/v1/callcenter/realtime/ws
```

## Notes

- Session memory for `callcenteragent` is stored in `backend/.data/callcenter_sessions.db`.
- The provider gateway currently implements only `openai_native`, but the interface is meant to stay
  stable for later provider benchmarking work.
- The live callcenter voice runtime now runs from Python over a backend WebSocket bridge instead of
  frontend-owned browser WebRTC agent orchestration.
