/**
 * PM2 process file - run from the repository root after installing dependencies
 * and building the Next.js frontend:
 *
 *   npm install
 *   uv sync --project backend
 *   uv sync --project backend_adk
 *   npm run build
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *
 * Ports:
 *   OpenAI FastAPI backend: 4011
 *   Google ADK FastAPI backend: 4012
 *   Next.js frontend: 3014
 *
 * This repo does not have a separate ./frontend directory. The Next app lives at
 * the repository root. The Python FastAPI apps live under ./backend and
 * ./backend_adk.
 *
 * Backend secrets such as OPENAI_API_KEY, GOOGLE_API_KEY, DEEPGRAM_API_KEY,
 * ELEVENLABS_API_KEY, MONGODB_URI, and MONGODB_DB can stay in the repo root
 * .env, backend/.env, backend_adk/.env, or be added under env below if you
 * prefer PM2-managed environment variables.
 *
 * The NEXT_PUBLIC_* values are included for runtime consistency, but client-side
 * Next.js public env vars should also be present when `npm run build` is run.
 * In HTTPS production, the browser WebSocket URL must be wss:// and must point
 * at a public backend/reverse-proxy hostname, not ws://127.0.0.1.
 *
 * The frontend can talk to only one backend target at a time. Build/start it
 * with the OpenAI backend endpoint, or switch FRONTEND_BACKEND_BASE_URL,
 * NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL, and NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL
 * to the ADK reverse-proxy endpoint before building.
 */
module.exports = {
  apps: [
    {
      name: "voice backend",
      cwd: ".",
      script: "uv",
      args:
        "run --project backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 4011 --proxy-headers",
      interpreter: "none",
      instances: 1,
      exec_mode: "fork",
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        BACKEND_PORT: "4011",
        BACKEND_BASE_URL: "http://127.0.0.1:4011",
        FRONTEND_BACKEND_BASE_URL: "http://127.0.0.1:4011",
        ALLOWED_ORIGINS: "http://127.0.0.1:3014,http://localhost:3014,https://demovoice.atenxion.ai",
        LOG_LEVEL: "INFO",
      },
    },
    {
      name: "voice backend adk",
      cwd: ".",
      script: "uv",
      args:
        "run --project backend_adk uvicorn app.main:app --app-dir backend_adk --host 0.0.0.0 --port 4012 --proxy-headers",
      interpreter: "none",
      instances: 1,
      exec_mode: "fork",
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        BACKEND_ADK_PORT: "4012",
        BACKEND_ADK_BASE_URL: "http://127.0.0.1:4012",
        FRONTEND_BACKEND_BASE_URL: "http://127.0.0.1:4012",
        ALLOWED_ORIGINS: "http://127.0.0.1:3014,http://localhost:3014,https://demovoice.atenxion.ai",
        GOOGLE_ADK_MODEL: "gemini-2.5-flash",
        VOICE_PROVIDER: "cascaded_pipeline",
        ADK_SESSION_DB_PATH: "backend_adk/.data/callcenter_sessions.db",
        CALLCENTER_SESSION_DB_PATH: "backend_adk/.data/callcenter_sessions.db",
        LOG_LEVEL: "INFO",
      },
    },
    {
      name: "voice frontend",
      cwd: ".",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 3014 -H 0.0.0.0",
      interpreter: "node",
      instances: 1,
      exec_mode: "fork",
      watch: false,
      env: {
        NODE_ENV: "production",
        PORT: "3014",
        FRONTEND_BACKEND_BASE_URL: "https://api-demovoice.atenxion.ai",
        NEXT_PUBLIC_FRONTEND_BACKEND_BASE_URL: "https://api-demovoice.atenxion.ai",
        NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL:
          "wss://api-demovoice.atenxion.ai/api/v1/callcenter/realtime/ws",
      },
    },
  ],
};
