"""Bridges browser WebSocket messages to an OpenAI RealtimeRunner session and normalizes realtime events back to frontend JSON."""
import asyncio
import base64
import contextlib
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.realtime import RealtimeRunner
from agents.realtime.model_inputs import RealtimeModelSendRawMessage
from fastapi import WebSocket, WebSocketDisconnect

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.realtime_graph import build_callcenter_realtime_agents
from app.agents.callcenter.session_audit import AuditedWebSocket, SessionAuditLogger
from app.core.config import Settings


def _serialize(value: Any) -> Any:
    """Convert SDK event objects, dataclasses, bytes, and Pydantic models into JSON-safe payloads."""
    if is_dataclass(value):
        return {key: _serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("utf-8")
    if hasattr(value, "model_dump"):
        return _serialize(value.model_dump())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {
            key: _serialize(val)
            for key, val in vars(value).items()
            if not key.startswith("_")
        }
    return value


class CallCenterRealtimeRuntime:
    """Runtime bridge between the browser WebSocket and OpenAI native realtime agent sessions."""
    def __init__(self, settings: Settings) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings
        self.agents = build_callcenter_realtime_agents()
        self.session_db_path = Path(settings.callcenter_session_db_path)
        self.session_db_path.parent.mkdir(parents=True, exist_ok=True)

    async def serve(self, websocket: WebSocket, agent_name: str | None = None) -> None:
        """Own the lifetime of one WebSocket session, initialize provider or SDK state, and coordinate reader and writer tasks."""
        await websocket.accept()

        starting_agent_name = agent_name or "callcenteragent"
        starting_agent = self.agents.get(starting_agent_name, self.agents["callcenteragent"])
        effective_session_id = f"callcenter-rt-{uuid4().hex}"
        trace_id = uuid4().hex
        context = CallCenterContext(
            session_id=effective_session_id,
            trace_id=trace_id,
        )
        context.current_agent_name = starting_agent.name
        audit_logger = SessionAuditLogger(self.settings)
        final_audit_status = "ended"
        await audit_logger.start_session(
            session_id=effective_session_id,
            trace_id=trace_id,
            architecture="openai_native",
            starting_agent=starting_agent.name,
        )
        audited_websocket = AuditedWebSocket(websocket, audit_logger, effective_session_id)

        runner = RealtimeRunner(
            starting_agent=starting_agent,
            config={
                "model_settings": {
                    "model_name": self.settings.realtime_model,
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "format": "pcm16",
                            "transcription": {
                                "model": "gpt-4o-mini-transcribe",
                            },
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.9,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                                "interrupt_response": True,
                            },
                        },
                        "output": {
                            "format": "pcm16",
                            "voice": "sage",
                        },
                    },
                    "tool_choice": "auto",
                },
                "tracing_disabled": False,
            },
        )
        session = await runner.run(
            context=context,
            model_config={
                "api_key": self.settings.openai_api_key,
            },
        )

        consumer_task: asyncio.Task[None] | None = None
        producer_task: asyncio.Task[None] | None = None

        try:
            async with session:
                await audited_websocket.send_json(
                    {
                        "type": "session_ready",
                        "session_id": effective_session_id,
                        "trace_id": trace_id,
                        "agent_name": starting_agent.name,
                        "architecture": "openai_native",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                consumer_task = asyncio.create_task(self._consume_client(audited_websocket, session))
                producer_task = asyncio.create_task(self._produce_events(audited_websocket, session))

                done, pending = await asyncio.wait(
                    {consumer_task, producer_task},
                    return_when=asyncio.FIRST_EXCEPTION,
                )

                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc

                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        except WebSocketDisconnect:
            pass
        except Exception:
            final_audit_status = "error"
            raise
        finally:
            if consumer_task and not consumer_task.done():
                consumer_task.cancel()
            if producer_task and not producer_task.done():
                producer_task.cancel()
            await audit_logger.end_session(effective_session_id, status=final_audit_status)
            with contextlib.suppress(Exception):
                await websocket.close()

    async def _consume_client(self, websocket: WebSocket, session: Any) -> None:
        """Read frontend WebSocket input and forward audio, text, interrupt, commit, and ping messages to the active session."""
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()

            if message.get("bytes") is not None:
                await session.send_audio(message["bytes"])
                continue

            if message.get("text") is None:
                continue

            payload = json.loads(message["text"])
            message_type = payload.get("type")

            if message_type == "user_text":
                await session.send_message(payload.get("text", ""))
            elif message_type == "interrupt":
                await session.interrupt()
            elif message_type == "client_event":
                event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
                await websocket.audit_logger.record_event(
                    websocket.session_id,
                    event,
                    direction="client",
                )
                await self._forward_supported_client_event(session, event)
            elif message_type == "audio_commit":
                await _send_raw_model_event(session, "input_audio_buffer.commit")
                await _send_raw_model_event(session, "response.create")
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})

    async def _forward_supported_client_event(self, session: Any, event: Any) -> None:
        """Apply browser control events that affect microphone turn-taking in the native realtime session."""
        if not isinstance(event, dict):
            return

        client_payload = event.get("payload")
        if not isinstance(client_payload, dict):
            return

        event_type = client_payload.get("type")
        if event_type == "input_audio_buffer.clear":
            await _send_raw_model_event(session, "input_audio_buffer.clear")
        elif event_type == "session.update":
            session_payload = client_payload.get("session")
            if isinstance(session_payload, dict):
                await _send_raw_model_event(
                    session,
                    "session.update",
                    {"session": session_payload},
                )

    async def _produce_events(self, websocket: WebSocket, session: Any) -> None:
        """Read provider or SDK events and stream normalized JSON payloads back to the frontend."""
        async for event in session:
            normalized = self._normalize_event(event)
            if normalized is not None:
                await websocket.send_json(normalized)

    def _normalize_event(self, event: Any) -> dict[str, Any] | None:
        """Map OpenAI realtime SDK event objects into the frontend event schema."""
        event_type = getattr(event, "type", None)
        if event_type == "audio":
            return {
                "type": "audio",
                "item_id": event.item_id,
                "content_index": event.content_index,
                "data": base64.b64encode(event.audio.data).decode("utf-8"),
            }
        if event_type == "audio_end":
            return {
                "type": "audio_end",
                "item_id": event.item_id,
                "content_index": event.content_index,
            }
        if event_type == "audio_interrupted":
            return {
                "type": "audio_interrupted",
                "item_id": event.item_id,
                "content_index": event.content_index,
            }
        if event_type == "history_added":
            return {
                "type": "history_added",
                "item": _serialize(event.item),
            }
        if event_type == "history_updated":
            return {
                "type": "history_updated",
                "history": _serialize(event.history),
            }
        if event_type == "tool_start":
            return {
                "type": "tool_start",
                "agent_name": event.agent.name,
                "tool_name": getattr(event.tool, "name", "unknown_tool"),
                "arguments": event.arguments,
            }
        if event_type == "tool_end":
            return {
                "type": "tool_end",
                "agent_name": event.agent.name,
                "tool_name": getattr(event.tool, "name", "unknown_tool"),
                "arguments": event.arguments,
                "output": _serialize(event.output),
            }
        if event_type == "handoff":
            return {
                "type": "handoff",
                "from_agent": event.from_agent.name,
                "to_agent": event.to_agent.name,
            }
        if event_type == "agent_start":
            return {
                "type": "agent_start",
                "agent_name": event.agent.name,
            }
        if event_type == "agent_end":
            return {
                "type": "agent_end",
                "agent_name": event.agent.name,
            }
        if event_type == "guardrail_tripped":
            return {
                "type": "guardrail_tripped",
                "message": getattr(event, "message", ""),
                "guardrail_results": _serialize(getattr(event, "guardrail_results", [])),
            }
        if event_type == "error":
            return {
                "type": "error",
                "error": str(getattr(event, "error", "unknown_error")),
            }
        if event_type == "raw_model_event":
            return {
                "type": "raw_model_event",
                "data": _serialize(event.data),
            }
        return None


async def _send_raw_model_event(
    session: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Send a raw Realtime API event through the Agents SDK without adding audio bytes."""
    await session.model.send_event(
        RealtimeModelSendRawMessage(
            message={
                "type": event_type,
                "other_data": payload or {},
            }
        )
    )
