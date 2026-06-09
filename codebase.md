# Codebase File Guide

This file is a quick, practical map of the repository. The whole system is a Next.js browser app that talks to a FastAPI voice backend. The default backend in `backend/` uses the OpenAI Agents SDK. The sibling backend in `backend_adk/` keeps the same frontend contract but uses Google ADK/Gemini for orchestration. The browser sends microphone audio and text through `useBackendRealtimeSession.ts`; the backend converts speech to text, runs a call-center agent graph, streams TTS audio back, and records useful audit events.

## End-to-End Picture

1. User opens `src/app/page.tsx`, which renders `src/app/App.tsx`.
2. `App.tsx` loads the call-center scenario from `src/app/agentConfigs/` and connects through `src/app/hooks/useBackendRealtimeSession.ts`.
3. Next.js API proxy routes under `src/app/api/` forward HTTP calls to the configured FastAPI backend.
4. The browser WebSocket connects to `/api/v1/callcenter/realtime/ws` in either `backend/` or `backend_adk/`.
5. The backend runtime receives audio/text, runs STT, calls the agent graph and tools, buffers sentences, sends ElevenLabs TTS audio, and emits transcript/event payloads.
6. Admin and stress-lab pages read the same backend data to inspect sessions and benchmark tool latency.

Example: a caller asks "Why is my bill higher?" The browser sends audio to the backend WebSocket, `runtime.py` transcribes it through Deepgram or ElevenLabs Scribe, the call-center graph routes to `billingAgent`, `tools.py` can call `get_latest_bill`, and the frontend transcript updates through `TranscriptContext.tsx`.

## Root Configuration and Docs

| File | What it does | Example contribution |
| --- | --- | --- |
| `README.md` | Main setup and run guide for this repo. | Tells a developer to run `npm run dev:backend` plus `npm run dev`. |
| `codebase.md` | This file; a file-by-file map of the project. | Helps a new teammate find where WebSocket voice logic lives. |
| `package.json` | Defines Node dependencies and npm scripts for frontend, backend, ADK backend, build, and tests. | `npm run dev:backend:adk` starts `backend_adk` on port `8001`. |
| `package-lock.json` | Locks exact npm dependency versions. | Makes `npm install` reproducible across machines. |
| `tsconfig.json` | TypeScript compiler settings for the Next.js app. | Allows `@/app/...` imports and React TSX checking. |
| `next.config.ts` | Next.js configuration. | Controls framework behavior for build and runtime. |
| `eslint.config.mjs` | ESLint configuration for TypeScript/Next.js code quality. | Used when linting frontend files. |
| `postcss.config.mjs` | PostCSS config used by Tailwind CSS. | Lets Tailwind process `globals.css`. |
| `tailwind.config.ts` | Tailwind theme/content configuration. | Makes classes in `src/app/**/*.tsx` available in compiled CSS. |
| `ecosystem.config.cjs` | PM2 production process file for frontend, OpenAI backend, and ADK backend. | Starts `voice backend`, `voice backend adk`, and `voice frontend` with production ports. |
| `.env.sample` | Local development environment template. | Shows `NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL=ws://127.0.0.1:8000/...`. |
| `.env.template` | Production endpoint template for the VM/domain setup. | Shows browser-facing `wss://api-demovoice.atenxion.ai/...`. |
| `LICENSE` | Project license text. | Explains reuse/legal terms for the code. |

## Public Assets

| File | What it does | Example contribution |
| --- | --- | --- |
| `public/favicon.ico` | Browser tab icon. | Shows the site icon when visiting `localhost:3000`. |
| `public/atenxion_logo.png` | Atenxion brand image used by the UI/docs. | Can be displayed in the app header or docs. |
| `public/openai-logomark.svg` | OpenAI logo asset inherited from the original demo. | Useful where OpenAI branding is shown. |
| `public/arrow.svg` | Small arrow image asset. | Can support simple visual UI affordances. |
| `public/call_center_flowchart_v1.png` | Architecture or flowchart image for call-center flow. | Used as a visual reference in docs or UI. |
| `public/screenshot_chat_supervisor.png` | Screenshot from the original chat-supervisor demo. | Historical reference for the original OpenAI sample. |
| `public/screenshot_handoff.png` | Screenshot from the original handoff demo. | Shows the upstream sequential handoff concept. |
| `public/filler_sounds/realistic_phone_ringing.wav` | Ringing sound used during transfer waits. | Plays while a handoff is being staged. |
| `public/filler_sounds/phone_transfer_ringing.mp3` | Transfer ring audio. | `useFillerAudio.ts` can loop it during a specialist transfer. |
| `public/filler_sounds/calm_office_background.wav` | Ambient background sound. | Can make the call-center demo feel less silent. |
| `public/filler_sounds/agent_typing.ogg` | Tool-wait typing sound. | Plays while a tool or backend action is running. |

## Explanatory Docs

| File | What it does | Example contribution |
| --- | --- | --- |
| `explainatory_docs/system_architecture_integration_handoff.md` | Markdown architecture handoff for integrating this demo into the larger Atenxion stack. | Explains browser, backend, ADK, and production route boundaries. |
| `explainatory_docs/system_architecture_integration_handoff.html` | Rendered HTML version of the architecture handoff. | Lets someone open the handoff in a browser. |
| `explainatory_docs/mcp_implementation_explanation.md` | Explains MCP connector/tool experiments in the call-center workflow. | Describes Gmail, email, and ticketing remote tool paths. |
| `explainatory_docs/mcp_after_action_log.md` | Notes what was implemented or observed for MCP work. | Useful when continuing MCP debugging. |
| `explainatory_docs/atenxion_bank_tool_explanation.md` | Explains the external Atenxion bank transaction lookup tool. | Helps trace why billing questions can call an external API. |

## Root Scripts

| File | What it does | Example contribution |
| --- | --- | --- |
| `scripts/seed_callcenter_mongo.py` | Seeds call-center mock data into MongoDB using the normal backend repository code. | Run it before using admin audit/RAG features locally. |
| `scripts/generate_atenxion_manual.py` | Generates a formatted Atenxion manual as document/PDF output. | Creates documentation artifacts from structured content. |

## Next.js App Shell

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/layout.tsx` | Root Next.js layout that wraps every page with global HTML/body structure. | Ensures `globals.css` applies to the app. |
| `src/app/page.tsx` | Main route for `/`; renders the voice application. | Visiting `localhost:3000` lands here. |
| `src/app/App.tsx` | Main client-side voice UI and state coordinator. | Connects the toolbar, transcript, event pane, filler audio, and backend realtime hook. |
| `src/app/globals.css` | Global CSS and Tailwind base styles. | Defines the base look of the entire frontend. |
| `src/app/types.ts` | Shared TypeScript types and Zod schemas for sessions, transcript items, events, and guardrails. | Keeps transcript and guardrail payload shapes consistent across components. |

## Frontend Contexts

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/contexts/EventContext.tsx` | Stores and logs client/server events for the right-side event pane. | When the backend emits `metrics_update`, this context lets the UI display it. |
| `src/app/contexts/TranscriptContext.tsx` | Stores conversation transcript messages and breadcrumbs. | Adds a breadcrumb like "Agent handoff to billingAgent". |

## Frontend Components

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/components/BottomToolbar.tsx` | Bottom control bar for connect/disconnect, mic, text input, push-to-talk, logs, and audio controls. | User clicks Connect here to open the backend realtime session. |
| `src/app/components/Events.tsx` | Event log UI for inspecting raw client/server event payloads. | Shows `session_ready`, `stt_partial`, and tool events while debugging. |
| `src/app/components/Transcript.tsx` | Transcript panel for user/assistant messages, tools, breadcrumbs, and guardrail states. | Displays the assistant's billing answer after TTS starts. |
| `src/app/components/GuardrailChip.tsx` | Small UI badge for guardrail/pass/fail state. | Marks a response as PASS after moderation completes. |

## Frontend Hooks and Utilities

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/hooks/useBackendRealtimeSession.ts` | Main browser-to-backend realtime hook for microphone capture, WebSocket events, PCM handling, TTS playback, interruption, and handoff callbacks. | Resolves `NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL` and streams audio to `/realtime/ws`. |
| `src/app/hooks/useRealtimeSession.ts` | Older direct OpenAI Realtime/WebRTC hook retained from the upstream demo. | Useful reference if comparing old browser-owned Realtime flow to backend-owned flow. |
| `src/app/hooks/useFillerAudio.ts` | Plays transfer ringing and tool-wait filler sounds. | Starts ringing when the backend emits transfer audio events. |
| `src/app/hooks/useHandleSessionHistory.ts` | Handles Realtime session history events for the older frontend-agent path. | Converts model events into transcript items in the legacy flow. |
| `src/app/hooks/useAudioDownload.ts` | Captures audio buffers for download/debugging. | Lets a developer save a session audio recording. |
| `src/app/lib/audioUtils.ts` | Audio conversion helpers, including PCM and WAV encoding. | Turns `Float32Array` microphone samples into WAV/PCM buffers. |
| `src/app/lib/codecUtils.ts` | WebRTC codec preference helper for the older direct Realtime path. | Can prefer Opus when using browser WebRTC. |
| `src/app/lib/envSetup.ts` | Frontend environment/setup helper. | Central place for browser config behavior. |
| `src/app/lib/speechActivityGate.ts` | Client-side speech activity detection helper. | Avoids sending accidental silence/noise as speech frames. |

## Frontend Pages

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/admin/page.tsx` | Admin review console for stored sessions, transcripts, events, and tickets. | A supervisor can inspect whether a call created an escalation ticket. |
| `src/app/stress-lab/page.tsx` | UI for running and reviewing call-center stress-lab scenarios. | Runs a mock billing-dispute latency scenario from the browser. |

## Frontend API Routes

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/api/_lib/backendProxy.ts` | Shared Next.js server-side proxy helper that forwards requests to `FRONTEND_BACKEND_BASE_URL`. | `/api/health` can call the FastAPI backend instead of local Next code. |
| `src/app/api/health/route.ts` | Next route for health checks, usually proxied to backend when configured. | Browser or deployment checks can hit `/api/health`. |
| `src/app/api/session/route.ts` | Next route for creating/retrieving session details, with proxy support. | Legacy direct OpenAI flow can request an ephemeral Realtime session. |
| `src/app/api/responses/route.ts` | Next route for OpenAI Responses calls, with proxy support. | Older supervisor-style flows can call a text model. |
| `src/app/api/admin/sessions/route.ts` | Proxies/list admin sessions for the admin UI. | `admin/page.tsx` loads recent sessions through this route. |
| `src/app/api/admin/sessions/[sessionId]/route.ts` | Proxies one admin session detail. | Opens transcript/events/tickets for a single call. |
| `src/app/api/stress-lab/scenarios/route.ts` | Proxies available stress-lab scenarios. | The stress lab page lists benchmark options from backend. |
| `src/app/api/stress-lab/runs/route.ts` | Proxies stress-lab run creation/listing. | Starts a backend latency benchmark. |
| `src/app/api/stress-lab/runs/[runId]/route.ts` | Proxies one stress-lab run result. | Shows detailed timing for a completed run. |

## Frontend Agent Configs

| File | What it does | Example contribution |
| --- | --- | --- |
| `src/app/agentConfigs/index.ts` | Registers available frontend scenario sets and default scenario. | Currently points the UI at `callcenteragent`. |
| `src/app/agentConfigs/types.ts` | Type definitions for frontend agent/scenario options. | Ensures every scenario has the labels and metadata the UI expects. |
| `src/app/agentConfigs/guardrails.ts` | Guardrail configuration for frontend-displayed responses. | Helps label unsafe or disallowed assistant content. |
| `src/app/agentConfigs/simpleHandoff.ts` | Simple handoff example from the original demo. | Shows the minimal pattern for transferring between agents. |
| `src/app/agentConfigs/voiceAgentMetaprompt.txt` | Prompt template/reference for designing voice agents. | Helps create new call-center style prompts. |
| `src/app/agentConfigs/callcenteragent/index.ts` | Frontend metadata for the Atenxion call-center scenario. | Populates scenario/agent dropdown names in the UI. |
| `src/app/agentConfigs/callcenteragent/prompts.ts` | Frontend prompt text for call-center agent display/legacy flows. | Mirrors backend intent for the UI-side config. |
| `src/app/agentConfigs/callcenteragent/tools.ts` | Frontend tool descriptors for the call-center scenario. | Lets the UI describe tools like `verifyCaller`. |
| `src/app/agentConfigs/callcenteragent/mockData.ts` | Frontend mock customer data. | Displays demo customer/service details without backend calls. |
| `src/app/agentConfigs/chatSupervisor/index.ts` | Original chat-supervisor scenario config. | Reference for hybrid realtime plus supervisor-agent pattern. |
| `src/app/agentConfigs/chatSupervisor/sampleData.ts` | Sample data for the chat-supervisor demo. | Provides fake customer details for the old scenario. |
| `src/app/agentConfigs/chatSupervisor/supervisorAgent.ts` | Supervisor agent definition for the original chat-supervisor flow. | Shows how a stronger text model can assist a realtime agent. |
| `src/app/agentConfigs/customerServiceRetail/index.ts` | Original retail customer-service scenario registration. | Demonstrates multi-specialist handoffs in frontend config. |
| `src/app/agentConfigs/customerServiceRetail/authentication.ts` | Authentication specialist for original retail demo. | Asks for identity information before returns/sales work. |
| `src/app/agentConfigs/customerServiceRetail/returns.ts` | Returns specialist for original retail demo. | Example of a domain-specific tool-heavy agent. |
| `src/app/agentConfigs/customerServiceRetail/sales.ts` | Sales specialist for original retail demo. | Handles buying/product questions in the legacy scenario. |
| `src/app/agentConfigs/customerServiceRetail/simulatedHuman.ts` | Simulated human escalation agent for original retail demo. | Demonstrates a fake live-agent transfer. |

## OpenAI Backend Project Files

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/README.md` | Backend-specific setup and endpoint documentation. | Lists `/api/v1/callcenter/realtime/ws`. |
| `backend/pyproject.toml` | Python dependencies and packaging for the OpenAI backend. | Installs FastAPI, `openai-agents`, Deepgram, ElevenLabs, and Motor. |
| `backend/uv.lock` | Locked Python dependency graph for `backend/`. | Makes backend installs reproducible. |
| `backend/app/__init__.py` | Marks `backend/app` as a Python package. | Allows imports like `app.main`. |
| `backend/app/main.py` | Creates the FastAPI app, CORS, request tracing, and router mounting. | `uvicorn app.main:app` starts here. |

## OpenAI Backend Core

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/app/core/__init__.py` | Package marker for core backend utilities. | Enables `app.core.config` imports. |
| `backend/app/core/config.py` | Pydantic settings loaded from env files. | Reads `OPENAI_API_KEY`, `VOICE_PROVIDER`, `MONGODB_URI`, and model names. |
| `backend/app/core/logging.py` | Logging setup and request ID context. | Adds traceable request IDs to backend logs. |
| `backend/app/core/mongo.py` | MongoDB client/database helper. | Lets session audit and data repository share Mongo access. |

## OpenAI Backend API

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/app/api/__init__.py` | Package marker for API modules. | Enables route imports. |
| `backend/app/api/router.py` | Combines health, session, responses, call-center, and stress-lab routers. | Mounts call-center routes under `/api/v1/callcenter`. |
| `backend/app/api/routes/health.py` | Health endpoint. | Returns backend status and config hints. |
| `backend/app/api/routes/session.py` | Session endpoint compatible with frontend expectations. | Provides backend session metadata to the browser. |
| `backend/app/api/routes/responses.py` | OpenAI Responses proxy endpoint. | Runs optional text/model helper calls server-side. |
| `backend/app/api/routes/callcenter.py` | Main call-center API: scenario metadata, text turns, admin session endpoints, seed route, and realtime WebSocket. | Accepts the browser voice WebSocket at `/realtime/ws`. |
| `backend/app/api/routes/stress_lab.py` | Stress-lab scenario and run endpoints. | Lets the frontend benchmark mock and hosted tool latency. |

## OpenAI Backend Voice Abstraction

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/app/voice/__init__.py` | Package marker for voice provider modules. | Enables provider imports. |
| `backend/app/voice/base.py` | Abstract voice provider interface. | Defines the contract for future voice providers. |
| `backend/app/voice/gateway.py` | Voice gateway selector/wrapper. | Chooses which voice provider should serve a session. |
| `backend/app/voice/openai_provider.py` | OpenAI-native voice provider implementation. | Used when testing `openai_native` architecture. |

## OpenAI Call-Center Agents

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/app/agents/__init__.py` | Package marker for agent modules. | Enables `app.agents.callcenter` imports. |
| `backend/app/agents/callcenter/__init__.py` | Package marker for call-center agent code. | Groups all Atenxion call-center logic. |
| `backend/app/agents/callcenter/context.py` | Per-session call-center state model. | Tracks verified caller, active case, and routing context. |
| `backend/app/agents/callcenter/prompts.py` | System prompts for triage, billing, support, retention, supervisor, and human escalation agents. | Defines how `billingAgent` should answer billing questions. |
| `backend/app/agents/callcenter/mock_data.py` | Canonical mock customers, bills, plans, policies, and RAG documents. | Supplies a fake customer profile for demo phone numbers. |
| `backend/app/agents/callcenter/data_repository.py` | Reads mock data and optionally MongoDB-backed records. | `lookup_customer_profile` can fall back to in-memory mock data. |
| `backend/app/agents/callcenter/tools.py` | Tool functions exposed to agents for verification, billing, support, retention, RAG, MCP, and cases. | `get_latest_bill` returns the caller's latest bill after verification. |
| `backend/app/agents/callcenter/bank_tool.py` | Client for external Atenxion Bank transaction lookup. | Billing can fetch transaction summaries for a user ID. |
| `backend/app/agents/callcenter/mcp_integrations.py` | Helpers for Gmail, email, and ticketing MCP connector calls. | Supervisor tools can search customer history via MCP when configured. |
| `backend/app/agents/callcenter/graph.py` | Builds the OpenAI Agents SDK text-agent graph and handoffs. | Routes a verified billing issue to `billingAgent`. |
| `backend/app/agents/callcenter/realtime_graph.py` | Builds OpenAI realtime agents for the native realtime path. | Supports direct OpenAI-native agent handoff experiments. |
| `backend/app/agents/callcenter/runner.py` | Text-only OpenAI Agents SDK turn runner. | `/api/v1/callcenter/run` uses it for non-voice requests. |
| `backend/app/agents/callcenter/realtime_runtime.py` | OpenAI-native realtime WebSocket runtime. | Bridges browser WebSocket events to OpenAI Realtime when selected. |
| `backend/app/agents/callcenter/session_audit.py` | Persists session events, transcripts, and derived tickets. | Admin page can later show a resolved billing ticket. |
| `backend/app/agents/callcenter/stress_lab.py` | Defines and runs benchmark scenarios for tool/API latency. | Measures how long a mock CRM lookup or bank API lookup takes. |

## OpenAI Cascaded Runtime

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/app/agents/callcenter/cascaded/__init__.py` | Package marker for cascaded voice runtime. | Groups STT, LLM, TTS, metrics, and event helpers. |
| `backend/app/agents/callcenter/cascaded/runtime.py` | Main cascaded coordinator: WebSocket receive loop, STT, OpenAI Agents SDK streaming, handoffs, sentence buffering, TTS, interruptions, and events. | Turns caller audio into a spoken billing-agent response. |
| `backend/app/agents/callcenter/cascaded/deepgram.py` | Deepgram streaming STT adapter and transcript aggregator. | Converts PCM audio into final transcript events. |
| `backend/app/agents/callcenter/cascaded/elevenlabs_stt.py` | ElevenLabs Scribe realtime STT adapter. | Enables the `elevenlabs_pipeline` architecture. |
| `backend/app/agents/callcenter/cascaded/elevenlabs.py` | ElevenLabs TTS streaming adapter. | Converts agent text sentences into PCM audio chunks. |
| `backend/app/agents/callcenter/cascaded/sentence_buffer.py` | Buffers streamed LLM text until complete spoken sentences are ready. | Prevents TTS from speaking half a sentence. |
| `backend/app/agents/callcenter/cascaded/text_normalization.py` | Normalizes numbers, money, dates, phone numbers, and identifiers for TTS. | Speaks `$42.18` naturally instead of as raw symbols. |
| `backend/app/agents/callcenter/cascaded/events.py` | Serializes backend events into frontend-compatible shapes. | Produces `response.audio.delta` style payloads for the UI. |
| `backend/app/agents/callcenter/cascaded/metrics.py` | Tracks turn latency, usage, and estimated cost. | Emits `metrics_update` events during a call. |

## OpenAI Backend Scripts

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/scripts/create_callcenter_vector_store.py` | Seeds RAG docs and creates/populates an OpenAI vector store. | Produces a `CALLCENTER_RAG_VECTOR_STORE_ID` for knowledge-base search. |
| `backend/scripts/probe_atenxion_bank_api.py` | Manual probe for the external Atenxion Bank API. | Checks whether transaction lookup credentials and payloads work. |

## OpenAI Backend Tests

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend/tests/conftest.py` | Shared pytest fixtures and environment setup. | Provides clean settings for backend tests. |
| `backend/tests/test_health.py` | Verifies health route behavior. | Confirms `/api/health` returns backend status. |
| `backend/tests/test_callcenter_metadata.py` | Verifies scenario metadata. | Ensures agent/tool names stay aligned with the frontend. |
| `backend/tests/test_callcenter_verification_failures.py` | Tests caller lookup and verification failure behavior. | Ensures unknown callers are not escalated incorrectly. |
| `backend/tests/test_callcenter_bank_tool.py` | Tests external bank API request/response normalization and verification requirements. | Confirms billing tools call the bank API safely. |
| `backend/tests/test_callcenter_mcp_tools.py` | Tests MCP helper tools and missing-config handling. | Confirms email/ticket tools explain missing server config. |
| `backend/tests/test_callcenter_rag.py` | Tests vector-store RAG search payloads and result normalization. | Ensures knowledge-base results are filtered and bounded. |
| `backend/tests/test_callcenter_mongo_audit.py` | Tests Mongo fallback data and session audit/ticket creation. | Confirms an outage call can create a field-service ticket. |
| `backend/tests/test_stress_lab.py` | Tests stress-lab scenario listing, skip logic, run persistence, and hosted tool cases. | Prevents benchmarks from failing when optional credentials are absent. |
| `backend/tests/test_cascaded_deepgram.py` | Tests Deepgram transcript aggregation and URL options. | Verifies `speech_final` and utterance-end behavior. |
| `backend/tests/test_cascaded_elevenlabs_stt.py` | Tests ElevenLabs Scribe STT options and event normalization. | Confirms Scribe uses PCM 16 kHz where expected. |
| `backend/tests/test_cascaded_sentence_and_tts.py` | Tests sentence buffering, TTS normalization, and ElevenLabs streaming. | Ensures abbreviations and money speak naturally. |
| `backend/tests/test_cascaded_runtime_events.py` | Tests runtime handoffs, fixed responses, interruption, audio events, and tool events. | Catches regressions in billing handoff audio behavior. |

## ADK Backend Project Files

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/README.md` | ADK backend-specific setup and architecture notes. | Explains Deepgram or ElevenLabs Scribe to Google ADK/Gemini to ElevenLabs. |
| `backend_adk/pyproject.toml` | Python dependencies and packaging for the ADK backend. | Installs `google-adk`, FastAPI, Deepgram, ElevenLabs, and OpenAI helpers. |
| `backend_adk/uv.lock` | Locked Python dependency graph for `backend_adk/`. | Makes ADK backend installs reproducible. |
| `backend_adk/app/__init__.py` | Package marker for the ADK app. | Enables `app.main` imports. |
| `backend_adk/app/main.py` | Creates the ADK FastAPI app, CORS, request tracing, and router mounting. | `uvicorn app.main:app --app-dir backend_adk` starts here. |

## ADK Backend Core

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/app/core/__init__.py` | Package marker for ADK core utilities. | Enables `app.core.config` imports. |
| `backend_adk/app/core/config.py` | ADK settings loaded from env files. | Reads `GOOGLE_API_KEY`, `GOOGLE_ADK_MODEL`, `BACKEND_ADK_PORT`, and voice provider config. |
| `backend_adk/app/core/logging.py` | Logging setup and request ID context for ADK backend. | Adds request IDs to ADK backend logs. |
| `backend_adk/app/core/mongo.py` | MongoDB helper for ADK backend. | Shares audit/data repository behavior with the OpenAI backend shape. |

## ADK Backend API

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/app/api/__init__.py` | Package marker for ADK API modules. | Enables route imports. |
| `backend_adk/app/api/router.py` | Combines ADK health, session, responses, call-center, and stress-lab routers. | Keeps route shape aligned with `backend/`. |
| `backend_adk/app/api/routes/health.py` | ADK health endpoint. | Returns backend status for `/api/health`. |
| `backend_adk/app/api/routes/session.py` | ADK session endpoint compatible with frontend expectations. | Lets the same frontend connect to the ADK backend. |
| `backend_adk/app/api/routes/responses.py` | Optional OpenAI Responses proxy route inside ADK backend. | Reports missing `OPENAI_API_KEY` when optional helpers are not configured. |
| `backend_adk/app/api/routes/callcenter.py` | ADK call-center API: scenario metadata, text turns, admin sessions, seed route, and ADK realtime WebSocket. | Exposes the same `/api/v1/callcenter/realtime/ws` contract using Google ADK. |
| `backend_adk/app/api/routes/stress_lab.py` | ADK stress-lab endpoints. | Lets benchmarks run against the ADK sibling backend. |

## ADK Voice Abstraction

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/app/voice/__init__.py` | Package marker for ADK voice modules. | Enables provider imports. |
| `backend_adk/app/voice/base.py` | Abstract voice provider interface. | Maintains a similar provider contract to the OpenAI backend. |
| `backend_adk/app/voice/gateway.py` | ADK voice gateway selector/wrapper. | Rejects unsupported OpenAI-native realtime and routes to cascaded providers. |

## ADK Call-Center Agents

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/app/agents/__init__.py` | Package marker for ADK agent modules. | Enables `app.agents.callcenter` imports. |
| `backend_adk/app/agents/callcenter/__init__.py` | Package marker for ADK call-center code. | Groups ADK prompts, tools, graph, runner, and runtime. |
| `backend_adk/app/agents/callcenter/context.py` | Per-session call-center state model. | Tracks verified caller and current specialist in ADK turns. |
| `backend_adk/app/agents/callcenter/prompts.py` | ADK call-center prompts, mostly aligned with the OpenAI backend. | Gives `retentionAgent` its cancellation-save behavior. |
| `backend_adk/app/agents/callcenter/mock_data.py` | ADK mock customers, bills, policies, and RAG documents. | Includes demo phone aliases accepted by ADK tools. |
| `backend_adk/app/agents/callcenter/data_repository.py` | ADK data repository with Mongo fallback behavior. | Allows ADK tools to read seeded or mock customer data. |
| `backend_adk/app/agents/callcenter/tools.py` | ADK-compatible tools for verification, cases, billing, support, retention, RAG, MCP, and external bank lookup. | ADK `billingAgent` can call `get_latest_bill`. |
| `backend_adk/app/agents/callcenter/bank_tool.py` | ADK copy of external Atenxion Bank lookup client. | Lets ADK billing flows query transactions. |
| `backend_adk/app/agents/callcenter/mcp_integrations.py` | ADK copy of MCP connector helpers. | Lets ADK supervisor flows use optional remote tools. |
| `backend_adk/app/agents/callcenter/graph.py` | Builds Google ADK `LlmAgent` specialists and transfer instructions. | Uses `transfer_to_agent` to move from triage to billing. |
| `backend_adk/app/agents/callcenter/runner.py` | Text-only ADK runner using ADK sessions and runner primitives. | `/api/v1/callcenter/run` can execute a Gemini-backed text turn. |
| `backend_adk/app/agents/callcenter/session_audit.py` | Persists ADK session events, transcripts, and derived tickets. | Admin page can inspect ADK calls like OpenAI calls. |
| `backend_adk/app/agents/callcenter/stress_lab.py` | ADK-compatible stress-lab service. | Benchmarks mock and hosted tool scenarios for ADK backend. |

## ADK Cascaded Runtime

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/app/agents/callcenter/cascaded/__init__.py` | Package marker for ADK cascaded voice runtime. | Groups ADK STT/TTS/runtime helpers. |
| `backend_adk/app/agents/callcenter/cascaded/runtime.py` | Main ADK cascaded coordinator: WebSocket audio, STT, Google ADK runner events, handoffs, sentence buffering, TTS, and frontend event normalization. | Turns caller speech into a Gemini/ADK specialist response with ElevenLabs audio. |
| `backend_adk/app/agents/callcenter/cascaded/deepgram.py` | Deepgram streaming STT adapter used by ADK runtime. | Produces final transcript events for ADK turns. |
| `backend_adk/app/agents/callcenter/cascaded/elevenlabs_stt.py` | ElevenLabs Scribe realtime STT adapter used by ADK runtime. | Enables ADK `elevenlabs_pipeline`. |
| `backend_adk/app/agents/callcenter/cascaded/elevenlabs.py` | ElevenLabs TTS adapter used by ADK runtime. | Streams Gemini/ADK response audio back to the browser. |
| `backend_adk/app/agents/callcenter/cascaded/sentence_buffer.py` | Buffers streamed ADK text until sentence-sized chunks are ready. | Keeps TTS from speaking partial tool narration. |
| `backend_adk/app/agents/callcenter/cascaded/text_normalization.py` | TTS normalization for ADK responses. | Makes account numbers and dates speak clearly. |
| `backend_adk/app/agents/callcenter/cascaded/events.py` | Event serialization helpers for ADK runtime. | Keeps frontend event shapes compatible with `Events.tsx`. |
| `backend_adk/app/agents/callcenter/cascaded/metrics.py` | ADK runtime latency and usage metrics. | Emits comparable cost/latency telemetry. |

## ADK Scripts

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/scripts/create_callcenter_vector_store.py` | Seeds ADK RAG docs and creates/populates an OpenAI vector store for optional RAG helpers. | Produces a vector store ID that ADK tools can use for knowledge-base search. |

## ADK Tests

| File | What it does | Example contribution |
| --- | --- | --- |
| `backend_adk/tests/conftest.py` | Shared pytest fixtures and environment setup for ADK tests. | Provides fake settings and isolated test state. |
| `backend_adk/tests/test_health.py` | Verifies ADK health route behavior. | Confirms `/api/health` works for the ADK backend. |
| `backend_adk/tests/test_callcenter_metadata.py` | Verifies ADK scenario metadata. | Ensures ADK does not advertise unsupported `openai_native`. |
| `backend_adk/tests/test_adk_graph_runner.py` | Tests ADK agent graph construction and text runner shape. | Confirms `LlmAgent` names match frontend expectations. |
| `backend_adk/tests/test_callcenter_verification_failures.py` | Tests ADK customer lookup and verification edge cases. | Confirms alternate phone numbers are accepted. |
| `backend_adk/tests/test_callcenter_rag.py` | Tests ADK RAG/vector-store and optional MCP helper behavior. | Ensures missing vector store config is reported clearly. |
| `backend_adk/tests/test_callcenter_mongo_audit.py` | Tests ADK Mongo fallback, seeding, audit logs, and ticket creation. | Confirms ADK sessions produce admin-review records. |
| `backend_adk/tests/test_stress_lab.py` | Tests ADK stress-lab listing, skip logic, runs, and persistence. | Prevents optional hosted benchmarks from breaking local tests. |
| `backend_adk/tests/test_cascaded_deepgram.py` | Tests ADK Deepgram transcript aggregation. | Confirms final transcript handling matches backend expectations. |
| `backend_adk/tests/test_cascaded_sentence_and_tts.py` | Tests ADK sentence buffering and ElevenLabs TTS behavior. | Ensures Gemini text streams are chunked into speakable sentences. |
| `backend_adk/tests/test_cascaded_runtime_events.py` | Tests ADK runtime handoffs, fixed replies, audio event ordering, and tool event normalization. | Catches regressions in ADK transfer audio and specialist routing. |

## System Examples

### Example 1: Local OpenAI backend voice call

1. `npm run dev:backend` starts `backend/app/main.py`.
2. `npm run dev` starts the Next.js app.
3. `src/app/App.tsx` calls `useBackendRealtimeSession.ts`.
4. The hook connects to `backend/app/api/routes/callcenter.py` at `/api/v1/callcenter/realtime/ws`.
5. `backend/app/agents/callcenter/cascaded/runtime.py` receives audio, uses `deepgram.py`, runs `graph.py` and `tools.py`, then speaks through `elevenlabs.py`.

### Example 2: Local ADK backend voice call

1. `npm run dev:backend:adk` starts `backend_adk/app/main.py`.
2. `.env` points `NEXT_PUBLIC_CALLCENTER_BACKEND_WS_URL` to port `8001`.
3. The same frontend hook connects to the ADK backend.
4. `backend_adk/app/agents/callcenter/cascaded/runtime.py` receives audio, runs Google ADK agents from `graph.py`, and returns the same frontend-compatible events.

### Example 3: Admin review after a call

1. During a call, `session_audit.py` records transcript and events.
2. `src/app/api/admin/sessions/route.ts` proxies admin list requests.
3. `src/app/admin/page.tsx` displays the session, events, transcript, and any generated tickets.

### Example 4: Stress-lab benchmark

1. `src/app/stress-lab/page.tsx` lists scenarios through `src/app/api/stress-lab/scenarios/route.ts`.
2. The route proxies to `backend/app/api/routes/stress_lab.py`.
3. `backend/app/agents/callcenter/stress_lab.py` runs scenarios such as mock CRM lookup or external bank lookup.
4. The UI displays latency, status, payload size, and skip reasons.
