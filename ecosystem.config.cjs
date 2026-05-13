/**
 * PM2 process file - run from the repository root after installing dependencies
 * and building the Next.js frontend:
 *
 *   npm install
 *   uv sync --project backend
 *   npm run build
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *
 * Ports: FastAPI backend 4011, Next.js frontend 3014.
 *
 * This repo does not have a separate ./frontend directory. The Next app lives at
 * the repository root, and the Python FastAPI app lives under ./backend.
 *
 * Backend secrets such as OPENAI_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY,
 * MONGODB_URI, and MONGODB_DB can stay in the repo root .env / backend/.env or
 * be added under env below if you prefer PM2-managed environment variables.
 *
 * The NEXT_PUBLIC_* values are included for runtime consistency, but client-side
 * Next.js public env vars should also be present when `npm run build` is run.
 */
module.exports = {
  apps: [
    {
      name: "atenxion-backend",
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
        ALLOWED_ORIGINS: "http://127.0.0.1:3014,http://localhost:3014, https://demovoice.atenxion.ai",
        LOG_LEVEL: "INFO",
      },
    },
    {
      name: "atenxion-frontend",
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
