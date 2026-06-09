# Cascaded Voice Demo

This repository contains the Atenxion call-center voice demo. It has three main pieces:

- A Next.js frontend at the project root.
- A FastAPI backend in `backend/` that runs the OpenAI Agents SDK call-center workflow.
- An optional FastAPI sibling backend in `backend_adk/` that runs the Google ADK version of the same call-center workflow.

The default local setup uses the root Next.js app on port `3000` and the OpenAI Agents backend on port `8000`.

## Prerequisites

- Node.js 20 or newer
- npm
- Python 3.11
- `uv` for Python dependency management
- API keys for the runtime you want to use:
  - `OPENAI_API_KEY` for the default `backend/` runtime
  - `DEEPGRAM_API_KEY` and `ELEVENLABS_API_KEY` for the cascaded voice pipeline
  - `GOOGLE_API_KEY` if you use `backend_adk/`
- Optional: MongoDB if you want seeded mock data and admin session audit storage

## Setup

Install frontend dependencies:

```powershell
npm install
```

Install backend dependencies:

```powershell
uv sync --project backend
```

Copy the example environment file:

```powershell
Copy-Item .env.sample .env
```

Edit `.env` and set at least:

```dotenv
OPENAI_API_KEY=your_openai_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key

FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=ws://127.0.0.1:8000/api/v1/callcenter/realtime/ws

BACKEND_PORT=8000
BACKEND_BASE_URL=http://127.0.0.1:8000
ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
VOICE_PROVIDER=cascaded_pipeline
```

`FRONTEND_BACKEND_BASE_URL` is used by the Next.js server-side proxy routes. The `NEXT_PUBLIC_*` values are browser-visible, so they must point to a URL the browser can reach.

## Run Locally

Start the default FastAPI backend:

```powershell
npm run dev:backend
```

In a second terminal, start the frontend:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000
```

Useful backend URLs:

- `GET http://127.0.0.1:8000/api/health`
- `GET http://127.0.0.1:8000/api/v1/callcenter/scenario`
- `WS ws://127.0.0.1:8000/api/v1/callcenter/realtime/ws`

## Run the ADK Backend

Use `backend_adk/` when you want the Google ADK version of the call-center orchestration. Install its dependencies:

```powershell
uv sync --project backend_adk
```

Update `.env` to point the frontend at port `8001`:

```dotenv
GOOGLE_API_KEY=your_google_ai_studio_key
GOOGLE_ADK_MODEL=gemini-2.5-flash
ADK_SESSION_DB_PATH=backend_adk/.data/callcenter_sessions.db
BACKEND_ADK_PORT=8001

FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8001
NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:8001
NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=ws://127.0.0.1:8001/api/v1/callcenter/realtime/ws
```

Start the ADK backend:

```powershell
npm run dev:backend:adk
```

Then run the frontend as usual:

```powershell
npm run dev
```

## Optional MongoDB and RAG Data

If MongoDB is running locally and `.env` has `MONGODB_URI` and `MONGODB_DB`, seed the call-center mock data with:

```powershell
uv run --project backend python scripts/seed_callcenter_mongo.py
```

For the ADK backend, the vector-store helper seeds MongoDB first, exports RAG documents, and creates an OpenAI vector store:

```powershell
uv run --project backend_adk python scripts/create_callcenter_vector_store.py
```

## Tests and Checks

Run backend tests:

```powershell
npm run test:backend
```

Run ADK backend tests:

```powershell
npm run test:backend:adk
```

Build the frontend:

```powershell
npm run build
```

If TypeScript needs to be checked directly on Windows, use:

```powershell
.\node_modules\.bin\tsc.cmd --noEmit
```

## Production Notes

The PM2 production process file is `ecosystem.config.cjs`. The included production shape is:

- FastAPI backend on port `4011`
- Next.js frontend on port `3014`
- Browser websocket URL set to `wss://api-demovoice.atenxion.ai/api/v1/callcenter/realtime/ws`

For production builds, set browser-visible `NEXT_PUBLIC_*` values before running:

```powershell
npm run build
```

Then start PM2 from the repository root:

```powershell
pm2 start ecosystem.config.cjs
pm2 save
```

Important env split:

- Server-side proxy values can point at private localhost services, such as `FRONTEND_BACKEND_BASE_URL=http://127.0.0.1:4011`.
- Browser-visible values must point at public HTTPS/WSS endpoints, such as `NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=wss://api-demovoice.atenxion.ai/api/v1/callcenter/realtime/ws`.
- Changing `NEXT_PUBLIC_*` values requires rebuilding the Next.js app and restarting the frontend process.

See `.env.template` for the current production endpoint template.

## Repository Map

- `src/app/` - Next.js app, UI, hooks, frontend API proxy routes, and agent config UI.
- `src/app/hooks/useBackendRealtimeSession.ts` - browser websocket session logic for backend-owned voice.
- `backend/` - FastAPI OpenAI Agents SDK backend.
- `backend/app/agents/callcenter/cascaded/runtime.py` - main cascaded voice runtime.
- `backend_adk/` - Google ADK backend implementation with matching route shape.
- `scripts/` - root-level helper scripts.
- `public/filler_sounds/` - audio assets used by the frontend.

## More Detail

- `backend/README.md` explains the OpenAI Agents backend endpoints and local workflow.
- `backend_adk/README.md` explains the Google ADK backend.
- `explainatory_docs/` contains architecture and integration notes for the broader Atenxion voice stack.
