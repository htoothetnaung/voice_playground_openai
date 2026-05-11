"""Exposes scenario metadata, a text turn endpoint, and the realtime WebSocket entry point for both supported voice architectures."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field

from app.agents.callcenter.cascaded.runtime import CallCenterCascadedRuntime
from app.agents.callcenter.data_repository import CallCenterDataRepository
from app.agents.callcenter.realtime_runtime import CallCenterRealtimeRuntime
from app.agents.callcenter.runner import CallCenterRunner
from app.agents.callcenter.session_audit import SessionAuditLogger
from app.core.config import Settings, get_settings

router = APIRouter()


class CallCenterRunRequest(BaseModel):
    """Groups the CallCenterRunRequest behavior or data used by this backend module."""
    input_text: str = Field(..., description="User input to run through the backend callcenteragent graph.")
    session_id: str | None = Field(
        default=None,
        description="Optional stable session identifier for conversation memory.",
    )


class CallCenterRunResponse(BaseModel):
    """Groups the CallCenterRunResponse behavior or data used by this backend module."""
    session_id: str
    final_output: Any
    trace: dict[str, Any]


class ClientSessionEventRequest(BaseModel):
    """Client-originated audit event payload for admin review."""
    direction: str = Field(default="client")
    event: dict[str, Any]


@router.get("/scenario")
async def scenario_metadata() -> dict[str, Any]:
    """Return static call-center scenario metadata used by the frontend to display available agents, tools, and architectures."""
    settings = get_settings()
    return {
        "scenario_key": "callcenteragent",
        "company_name": "Atenxion",
        "voice_provider": settings.voice_provider,
        "available_architectures": [
            {
                "id": "openai_native",
                "label": "OpenAI Native Realtime",
                "stt_provider": "openai",
                "llm_provider": "openai",
                "tts_provider": "openai",
                "default_model": settings.realtime_model,
            },
            {
                "id": "cascaded_pipeline",
                "label": "Deepgram -> GPT-4.1 mini -> ElevenLabs",
                "stt_provider": "deepgram",
                "stt_models": [settings.deepgram_stt_model, settings.deepgram_stt_alt_model],
                "llm_provider": "openai",
                "llm_model": settings.cascaded_llm_model,
                "tts_provider": "elevenlabs",
                "tts_models": [settings.elevenlabs_tts_model, settings.elevenlabs_tts_alt_model],
            },
        ],
        "agents": [
            "callcenteragent",
            "billingAgent",
            "technicalSupportAgent",
            "retentionAgent",
            "supervisorAgent",
            "humanEscalationAgent",
        ],
        "tools": {
            "shared": [
                "lookupCustomerProfile",
                "verifyCaller",
                "lookupActiveServices",
                "createCase",
                "addCaseNote",
            ],
            "billing": [
                "getLatestBill",
                "explainChargeBreakdown",
                "offerPaymentArrangement",
                "applyGoodwillCredit",
            ],
            "technical_support": [
                "checkServiceOutage",
                "runLineDiagnostics",
                "scheduleTechnician",
                "rebootDeviceWorkflow",
            ],
            "retention": [
                "lookupPlanOptions",
                "comparePlans",
                "generateRetentionOffer",
                "submitCancellationRequest",
            ],
            "supervisor": [
                "lookupPolicyDocument",
                "approveException",
                "escalationDecision",
            ],
        },
    }


@router.post("/seed")
async def seed_callcenter_mock_data(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Seed the current demo mock records into MongoDB when a local server is available."""
    seeded = await CallCenterDataRepository(settings).seed_mock_data()
    return {
        "seeded": seeded,
        "database": settings.mongodb_db,
        "mongo_available": seeded,
    }


@router.post("/sessions/{session_id}/events")
async def record_client_session_event(
    session_id: str,
    payload: ClientSessionEventRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Persist a client-side event for admin review without storing raw audio."""
    await SessionAuditLogger(settings).record_event(
        session_id,
        payload.event,
        direction=payload.direction,
    )
    return {"accepted": True}


@router.get("/admin/sessions")
async def list_admin_sessions(
    limit: int = 25,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return recent stored sessions for the admin console."""
    sessions = await SessionAuditLogger(settings).list_sessions(limit=max(1, min(limit, 100)))
    return {"sessions": sessions}


@router.get("/admin/sessions/{session_id}")
async def get_admin_session_detail(
    session_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return transcript, event, and ticket details for one stored session."""
    detail = await SessionAuditLogger(settings).session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.post("/run", response_model=CallCenterRunResponse)
async def run_callcenter_turn(
    payload: CallCenterRunRequest,
    settings: Settings = Depends(get_settings),
) -> CallCenterRunResponse:
    """Run one text-only call-center turn through the OpenAI Agents SDK graph and return the trace payload."""
    runner = CallCenterRunner(settings)
    result = await runner.run_turn(
        input_text=payload.input_text,
        session_id=payload.session_id,
    )
    return CallCenterRunResponse(**result)


@router.websocket("/realtime/ws")
async def callcenter_realtime_ws(websocket: WebSocket) -> None:
    """Accept the call-center WebSocket and choose either OpenAI native realtime or the cascaded voice runtime."""
    settings = get_settings()
    architecture = websocket.query_params.get("architecture") or settings.voice_provider
    if architecture == "openai_native" and settings.voice_provider == "openai_native":
        architecture = "cascaded_pipeline"
    if architecture == "cascaded_pipeline":
        runtime = CallCenterCascadedRuntime(settings)
    else:
        runtime = CallCenterRealtimeRuntime(settings)
    await runtime.serve(
        websocket,
        agent_name=websocket.query_params.get("agent_name"),
    )
