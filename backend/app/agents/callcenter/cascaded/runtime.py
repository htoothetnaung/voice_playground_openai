"""Coordinates browser audio/text, Deepgram transcripts, OpenAI Agents SDK streamed LLM responses, ElevenLabs audio, handoff audio cues, history events, and metrics."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents import Runner, SQLiteSession
from fastapi import WebSocket, WebSocketDisconnect

from app.agents.callcenter.cascaded.deepgram import (
    DeepgramStreamingTranscriber,
    TranscriptEvent,
)
from app.agents.callcenter.cascaded.elevenlabs import ElevenLabsTTSAdapter
from app.agents.callcenter.cascaded.events import audio_event, message_item, serialize
from app.agents.callcenter.cascaded.metrics import TurnMetrics
from app.agents.callcenter.cascaded.sentence_buffer import SentenceBuffer
from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.graph import build_callcenter_agent_map
from app.agents.callcenter.session_audit import AuditedWebSocket, SessionAuditLogger
from app.core.config import Settings

HANDOFF_TRANSFER_DELAY_SECONDS = 2.5
MAX_AGENT_TURNS = 30
PCM_BYTES_PER_SAMPLE = 2
MIN_TTS_AUDIO_FRAME_MS = 40

AGENT_DISPLAY_DETAILS = {
    "callcenteragent": ("Alice", "front desk"),
    "billingAgent": ("Austin", "billing"),
    "technicalSupportAgent": ("Bob", "technical support"),
    "retentionAgent": ("Maya", "retention"),
    "supervisorAgent": ("Sarah", "floor supervisor"),
    "humanEscalationAgent": ("Jordan", "escalation desk"),
}


class CallCenterCascadedRuntime:
    """Runtime that coordinates Deepgram STT, OpenAI Agents SDK streaming, ElevenLabs TTS, and frontend WebSocket events."""
    architecture = "cascaded_pipeline"

    def __init__(
        self,
        settings: Settings,
        transcriber: DeepgramStreamingTranscriber | None = None,
        tts_adapter: ElevenLabsTTSAdapter | None = None,
    ) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        self.agents = build_callcenter_agent_map(model=settings.cascaded_llm_model)
        self.session_db_path = Path(settings.callcenter_session_db_path)
        self.session_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcriber = transcriber
        self.tts_adapter = tts_adapter
        self._active_stt_metrics: TurnMetrics | None = None
        self._response_task: asyncio.Task[None] | None = None

    async def serve(self, websocket: WebSocket, agent_name: str | None = None) -> None:
        """Own the lifetime of one WebSocket session, initialize provider or SDK state, and coordinate reader and writer tasks."""
        await websocket.accept()

        starting_agent_name = agent_name or "callcenteragent"
        starting_agent = self.agents.get(starting_agent_name, self.agents["callcenteragent"])
        effective_session_id = f"callcenter-cascaded-{uuid4().hex}"
        trace_id = uuid4().hex
        context = CallCenterContext(session_id=effective_session_id, trace_id=trace_id)
        context.current_agent_name = starting_agent.name
        session = SQLiteSession(effective_session_id, str(self.session_db_path))
        audit_logger = SessionAuditLogger(self.settings)
        final_audit_status = "ended"
        await audit_logger.start_session(
            session_id=effective_session_id,
            trace_id=trace_id,
            architecture=self.architecture,
            starting_agent=starting_agent.name,
        )
        audited_websocket = AuditedWebSocket(websocket, audit_logger, effective_session_id)

        transcriber = self.transcriber or self._build_transcriber()
        tts_adapter = self.tts_adapter or self._build_tts_adapter()
        consumer_task: asyncio.Task[None] | None = None
        transcript_task: asyncio.Task[None] | None = None

        try:
            if transcriber is not None:
                try:
                    await transcriber.start()
                except Exception as exc:
                    await audited_websocket.send_json(
                        {
                            "type": "error",
                            "error": f"Deepgram STT connection failed: {exc}",
                        }
                    )
                    transcriber = None
            if transcriber is None:
                await audited_websocket.send_json(
                    {
                        "type": "error",
                        "error": "Microphone transcription is disabled; text messages can still use the cascaded agent/TTS path.",
                    }
                )

            await audited_websocket.send_json(
                {
                    "type": "session_ready",
                    "session_id": effective_session_id,
                    "trace_id": trace_id,
                    "agent_name": starting_agent.name,
                    "architecture": self.architecture,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            await audited_websocket.send_json(
                {
                    "type": "architecture_selected",
                    "architecture": self.architecture,
                    "stt_model": self.settings.deepgram_stt_model,
                    "llm_model": self.settings.cascaded_llm_model,
                    "tts_model": self.settings.elevenlabs_tts_model,
                }
            )

            consumer_task = asyncio.create_task(
                self._consume_client(audited_websocket, transcriber, starting_agent, context, session, tts_adapter)
            )
            if transcriber is not None:
                transcript_task = asyncio.create_task(
                    self._consume_transcripts(audited_websocket, transcriber, starting_agent, context, session, tts_adapter)
                )

            wait_tasks = {consumer_task}
            if transcript_task is not None:
                wait_tasks.add(transcript_task)
            done, pending = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_EXCEPTION)
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
            if self._response_task and not self._response_task.done():
                self._response_task.cancel()
            for task in (consumer_task, transcript_task):
                if task and not task.done():
                    task.cancel()
            if transcriber is not None:
                await transcriber.close()
            await audit_logger.end_session(effective_session_id, status=final_audit_status)
            with contextlib.suppress(Exception):
                await websocket.close()

    def _build_transcriber(self) -> DeepgramStreamingTranscriber | None:
        """Create the Deepgram adapter when STT credentials are configured."""
        if not self.settings.deepgram_api_key:
            return None
        return DeepgramStreamingTranscriber(
            api_key=self.settings.deepgram_api_key,
            model=self.settings.deepgram_stt_model,
            sample_rate=self.settings.cascaded_input_sample_rate,
            endpointing_ms=self.settings.deepgram_endpointing_ms,
            utterance_end_ms=self.settings.deepgram_utterance_end_ms,
        )

    def _build_tts_adapter(self) -> ElevenLabsTTSAdapter | None:
        """Create the ElevenLabs adapter when TTS credentials are configured."""
        if not self.settings.elevenlabs_api_key:
            return None
        return ElevenLabsTTSAdapter(
            api_key=self.settings.elevenlabs_api_key,
            voice_id=self.settings.elevenlabs_voice_id,
            model=self.settings.elevenlabs_tts_model,
            sample_rate=self.settings.cascaded_output_sample_rate,
            timeout_seconds=self.settings.cascaded_provider_timeout_seconds,
        )

    async def _consume_client(
        self,
        websocket: WebSocket,
        transcriber: DeepgramStreamingTranscriber | None,
        starting_agent: Any,
        context: CallCenterContext,
        session: SQLiteSession,
        tts_adapter: ElevenLabsTTSAdapter | None,
    ) -> None:
        """Read frontend WebSocket input and forward audio, text, interrupt, commit, and ping messages to the active session."""
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()

            if message.get("bytes") is not None:
                if self._active_stt_metrics is None:
                    self._active_stt_metrics = self._new_metrics()
                self._active_stt_metrics.user_audio_bytes += len(message["bytes"])
                if transcriber is not None:
                    try:
                        await transcriber.send_audio(message["bytes"])
                    except Exception as exc:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": f"Deepgram STT stream unavailable: {exc}",
                            }
                        )
                        transcriber = None
                continue

            if message.get("text") is None:
                continue

            payload = _loads(message["text"])
            message_type = payload.get("type")
            if message_type == "user_text":
                await self._start_agent_turn(
                    websocket,
                    text=payload.get("text", ""),
                    starting_agent=starting_agent,
                    context=context,
                    session=session,
                    tts_adapter=tts_adapter,
                    metrics=self._new_metrics(),
                )
            elif message_type == "interrupt":
                if self._response_task and not self._response_task.done():
                    self._response_task.cancel()
                await websocket.send_json({"type": "audio_interrupted"})
            elif message_type == "client_event":
                await websocket.audit_logger.record_event(
                    websocket.session_id,
                    payload.get("event") if isinstance(payload.get("event"), dict) else payload,
                    direction="client",
                )
            elif message_type == "audio_commit" and transcriber is not None:
                await transcriber.flush_audio()
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})

    async def _consume_transcripts(
        self,
        websocket: WebSocket,
        transcriber: DeepgramStreamingTranscriber,
        starting_agent: Any,
        context: CallCenterContext,
        session: SQLiteSession,
        tts_adapter: ElevenLabsTTSAdapter | None,
    ) -> None:
        """Consume Deepgram transcript events and start an OpenAI agent turn when speech finalizes."""
        while True:
            event = await transcriber.events.get()
            metrics = self._active_stt_metrics or self._new_metrics()
            if event.event_type == "stt_partial":
                if metrics.stt_first_partial_ms is None:
                    metrics.stt_first_partial_ms = metrics.mark_ms()
                await websocket.send_json({"type": "stt_partial", "text": event.text, "raw": event.raw})
                continue

            if event.event_type == "stt_final":
                if metrics.stt_first_final_ms is None:
                    metrics.stt_first_final_ms = metrics.mark_ms()
                await websocket.send_json(
                    {
                        "type": "stt_final",
                        "text": event.text,
                        "is_final": event.is_final,
                        "speech_final": event.speech_final,
                    }
                )
                if not event.speech_final:
                    continue

                metrics.turn_detected_ms = metrics.mark_ms()
                await websocket.send_json({"type": "turn_detected", "text": event.text})
                self._active_stt_metrics = None
                await self._start_agent_turn(
                    websocket,
                    text=event.text,
                    starting_agent=starting_agent,
                    context=context,
                    session=session,
                    tts_adapter=tts_adapter,
                    metrics=metrics,
                )

    async def _start_agent_turn(
        self,
        websocket: WebSocket,
        text: str,
        starting_agent: Any,
        context: CallCenterContext,
        session: SQLiteSession,
        tts_adapter: ElevenLabsTTSAdapter | None,
        metrics: TurnMetrics,
    ) -> None:
        """Cancel any active response and launch a new cascaded LLM/TTS turn for clean user text."""
        clean_text = text.strip()
        if not clean_text:
            return
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            await websocket.send_json({"type": "audio_interrupted"})

        self._response_task = asyncio.create_task(
            self._run_agent_turn(
                websocket,
                clean_text,
                starting_agent,
                context,
                session,
                tts_adapter,
                metrics,
            )
        )

    async def _run_agent_turn(
        self,
        websocket: WebSocket,
        text: str,
        starting_agent: Any,
        context: CallCenterContext,
        session: SQLiteSession,
        tts_adapter: ElevenLabsTTSAdapter | None,
        metrics: TurnMetrics,
    ) -> None:
        """Stream one OpenAI Agents SDK turn, manage handoffs, queue sentences for TTS, and emit final history and metrics."""
        metrics.user_text = text
        user_item_id = f"user-{uuid4().hex}"
        assistant_item_id = f"assistant-{uuid4().hex}"
        active_agent_name = context.current_agent_name or starting_agent.name
        handoff_transfer_pending = False
        pending_handoff_agent_name: str | None = None
        sentence_buffer = SentenceBuffer(min_length=18)
        sentence_queue: asyncio.Queue[tuple[str, bool, str] | None] = asyncio.Queue()
        assistant_text_parts: list[str] = []
        tts_worker = asyncio.create_task(
            self._tts_worker(websocket, sentence_queue, assistant_item_id, tts_adapter, metrics)
        )

        try:
            await websocket.send_json({"type": "history_added", "item": message_item(user_item_id, "user", text)})
            await websocket.send_json({"type": "agent_start", "agent_name": active_agent_name})

            fixed_response = _fixed_response_for_user_text(text, context, active_agent_name)
            if fixed_response:
                if metrics.first_sentence_ms is None:
                    metrics.first_sentence_ms = metrics.mark_ms()
                assistant_text_parts.append(f"{fixed_response} ")
                await sentence_queue.put((fixed_response, False, active_agent_name))
            else:
                run_agent = self.agents.get(active_agent_name, starting_agent)
                direct_handoff_agent_name = _direct_handoff_agent_name(
                    text,
                    active_agent_name,
                    is_verified=context.verified,
                )
                if direct_handoff_agent_name and direct_handoff_agent_name in self.agents:
                    previous_agent_name = active_agent_name
                    active_agent_name = direct_handoff_agent_name
                    context.current_agent_name = active_agent_name
                    run_agent = self.agents[direct_handoff_agent_name]
                    display_name, team = _agent_display_details(direct_handoff_agent_name)
                    await websocket.send_json(
                        {
                            "type": "handoff",
                            "from_agent": previous_agent_name,
                            "to_agent": direct_handoff_agent_name,
                            "to_agent_display_name": display_name,
                            "to_agent_team": team,
                            "reason": "deterministic_intent_route",
                        }
                    )
                    handoff_outro = _handoff_outro(previous_agent_name, direct_handoff_agent_name)
                    handoff_intro = _handoff_intro(previous_agent_name, direct_handoff_agent_name)
                    metrics.first_sentence_ms = metrics.first_sentence_ms or metrics.mark_ms()
                    assistant_text_parts.append(f"{handoff_outro} ")
                    await sentence_queue.put((handoff_outro, False, previous_agent_name))
                    assistant_text_parts.append(f"{handoff_intro} ")
                    await sentence_queue.put((handoff_intro, True, active_agent_name))
                    pending_handoff_agent_name = active_agent_name

                result = Runner.run_streamed(
                    run_agent,
                    input=text,
                    context=context,
                    session=session,
                    max_turns=MAX_AGENT_TURNS,
                )

                async for event in result.stream_events():
                    delta = _extract_text_delta(event)
                    if delta:
                        if metrics.llm_first_token_ms is None:
                            metrics.llm_first_token_ms = metrics.mark_ms()
                        for sentence in sentence_buffer.add(delta):
                            if _should_skip_agent_sentence(sentence, active_agent_name, pending_handoff_agent_name):
                                continue
                            pending_handoff_agent_name = None
                            if metrics.first_sentence_ms is None:
                                metrics.first_sentence_ms = metrics.mark_ms()
                            assistant_text_parts.append(f"{sentence} ")
                            await sentence_queue.put((sentence, handoff_transfer_pending, active_agent_name))
                            handoff_transfer_pending = False
                        continue

                    if getattr(event, "type", None) == "agent_updated_stream_event":
                        new_agent_name = event.new_agent.name
                        if new_agent_name != active_agent_name:
                            previous_agent_name = active_agent_name
                            display_name, team = _agent_display_details(new_agent_name)
                            pre_handoff_remaining = sentence_buffer.flush()
                            if pre_handoff_remaining and not _should_skip_agent_sentence(
                                pre_handoff_remaining,
                                previous_agent_name,
                                new_agent_name,
                            ):
                                if metrics.first_sentence_ms is None:
                                    metrics.first_sentence_ms = metrics.mark_ms()
                                assistant_text_parts.append(f"{pre_handoff_remaining} ")
                                await sentence_queue.put(
                                    (pre_handoff_remaining, handoff_transfer_pending, previous_agent_name)
                                )
                                handoff_transfer_pending = False
                            await websocket.send_json(
                                {
                                    "type": "handoff",
                                    "from_agent": previous_agent_name,
                                    "to_agent": new_agent_name,
                                    "to_agent_display_name": display_name,
                                    "to_agent_team": team,
                                }
                            )
                            handoff_outro = _handoff_outro(previous_agent_name, new_agent_name)
                            handoff_intro = _handoff_intro(previous_agent_name, new_agent_name)
                            if metrics.first_sentence_ms is None:
                                metrics.first_sentence_ms = metrics.mark_ms()
                            assistant_text_parts.append(f"{handoff_outro} ")
                            await sentence_queue.put((handoff_outro, False, previous_agent_name))
                            active_agent_name = new_agent_name
                            context.current_agent_name = active_agent_name
                            if metrics.first_sentence_ms is None:
                                metrics.first_sentence_ms = metrics.mark_ms()
                            assistant_text_parts.append(f"{handoff_intro} ")
                            await sentence_queue.put((handoff_intro, True, active_agent_name))
                            handoff_transfer_pending = False
                            pending_handoff_agent_name = active_agent_name
                        continue

                    if getattr(event, "type", None) == "run_item_stream_event":
                        await self._send_run_item_event(websocket, event, active_agent_name)

                remaining = sentence_buffer.flush()
                if remaining:
                    if not _should_skip_agent_sentence(remaining, active_agent_name, pending_handoff_agent_name):
                        pending_handoff_agent_name = None
                        if metrics.first_sentence_ms is None:
                            metrics.first_sentence_ms = metrics.mark_ms()
                        assistant_text_parts.append(f"{remaining} ")
                        await sentence_queue.put((remaining, handoff_transfer_pending, active_agent_name))

            await sentence_queue.put(None)
            await tts_worker
            assistant_text = "".join(assistant_text_parts).strip()
            metrics.assistant_text = assistant_text
            metrics.finish()
            await websocket.send_json(
                {"type": "history_added", "item": message_item(assistant_item_id, "assistant", assistant_text)}
            )
            await websocket.send_json({"type": "audio_end", "item_id": assistant_item_id, "content_index": 0})
            await websocket.send_json({"type": "agent_end", "agent_name": active_agent_name})
            context.current_agent_name = active_agent_name
            await websocket.send_json({"type": "metrics_update", **metrics.as_event_payload()})
            await websocket.send_json({"type": "cost_estimate", **metrics.cost_estimate()})
        except asyncio.CancelledError:
            tts_worker.cancel()
            await websocket.send_json({"type": "audio_interrupted"})
            raise
        except Exception as exc:
            tts_worker.cancel()
            await websocket.send_json({"type": "error", "error": f"cascaded_turn_failed: {exc}"})

    async def _tts_worker(
        self,
        websocket: WebSocket,
        sentence_queue: asyncio.Queue[tuple[str, bool, str] | None],
        assistant_item_id: str,
        tts_adapter: ElevenLabsTTSAdapter | None,
        metrics: TurnMetrics,
    ) -> None:
        """Read completed sentences, apply handoff delays, stream ElevenLabs audio, and emit speaking events."""
        speaking_agent_name: str | None = None
        while True:
            queue_item = await sentence_queue.get()
            if queue_item is None:
                if speaking_agent_name is not None:
                    await websocket.send_json(
                        {"type": "agent_speech_end", "agent_name": speaking_agent_name}
                    )
                return
            sentence, delay_for_handoff, agent_name = queue_item
            if agent_name != speaking_agent_name:
                if speaking_agent_name is not None:
                    await websocket.send_json(
                        {"type": "agent_speech_end", "agent_name": speaking_agent_name}
                    )
                speaking_agent_name = None
            if delay_for_handoff:
                await websocket.send_json(
                    {
                        "type": "transfer_audio_start",
                        "agent_name": agent_name,
                        "duration_ms": round(HANDOFF_TRANSFER_DELAY_SECONDS * 1000),
                    }
                )
                await asyncio.sleep(HANDOFF_TRANSFER_DELAY_SECONDS)
                await websocket.send_json(
                    {
                        "type": "transfer_audio_end",
                        "agent_name": agent_name,
                    }
                )
            if speaking_agent_name is None:
                speaking_agent_name = agent_name
                await websocket.send_json(
                    {"type": "agent_speech_start", "agent_name": agent_name}
                )
            metrics.tts_characters += len(sentence)
            if tts_adapter is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "ELEVENLABS_API_KEY is not configured; TTS audio is disabled.",
                    }
                )
                continue
            voice_id = _agent_voice_id(agent_name, self.settings)
            pending_audio = b""
            min_frame_bytes = round(
                self.settings.cascaded_output_sample_rate
                * PCM_BYTES_PER_SAMPLE
                * MIN_TTS_AUDIO_FRAME_MS
                / 1000
            )
            async for chunk in tts_adapter.synthesize_stream(sentence, voice_id=voice_id):
                if metrics.tts_first_audio_ms is None:
                    metrics.tts_first_audio_ms = metrics.mark_ms()
                pending_audio += chunk
                emit_length = len(pending_audio) - (len(pending_audio) % PCM_BYTES_PER_SAMPLE)
                if emit_length < min_frame_bytes:
                    continue
                audio_bytes = pending_audio[:emit_length]
                pending_audio = pending_audio[emit_length:]
                metrics.output_audio_bytes += len(audio_bytes)
                await websocket.send_json(audio_event(assistant_item_id, 0, audio_bytes, agent_name=agent_name))

            if len(pending_audio) >= PCM_BYTES_PER_SAMPLE:
                emit_length = len(pending_audio) - (len(pending_audio) % PCM_BYTES_PER_SAMPLE)
                audio_bytes = pending_audio[:emit_length]
                metrics.output_audio_bytes += len(audio_bytes)
                await websocket.send_json(audio_event(assistant_item_id, 0, audio_bytes, agent_name=agent_name))

    async def _send_run_item_event(self, websocket: WebSocket, event: Any, active_agent_name: str) -> None:
        """Translate OpenAI Agents SDK tool-call stream events into frontend tool_start/tool_end events."""
        item = getattr(event, "item", None)
        event_name = getattr(event, "name", "")
        if event_name == "tool_called":
            await websocket.send_json(
                {
                    "type": "tool_start",
                    "agent_name": active_agent_name,
                    "tool_name": _extract_tool_name(item),
                    "arguments": _extract_tool_arguments(item),
                }
            )
        elif event_name == "tool_output":
            await websocket.send_json(
                {
                    "type": "tool_end",
                    "agent_name": active_agent_name,
                    "tool_name": _extract_tool_name(item),
                    "arguments": _extract_tool_arguments(item),
                    "output": serialize(_extract_tool_output(item)),
                }
            )

    def _new_metrics(self) -> TurnMetrics:
        """Create a TurnMetrics object populated with the active cascaded provider and model settings."""
        return TurnMetrics(
            architecture=self.architecture,
            stt_provider="deepgram",
            stt_model=self.settings.deepgram_stt_model,
            llm_provider="openai",
            llm_model=self.settings.cascaded_llm_model,
            tts_provider="elevenlabs",
            tts_model=self.settings.elevenlabs_tts_model,
            tts_voice_id=self.settings.elevenlabs_voice_id,
            input_sample_rate=self.settings.cascaded_input_sample_rate,
            output_sample_rate=self.settings.cascaded_output_sample_rate,
        )


def _loads(text: str) -> dict[str, Any]:
    """Safely parse a frontend text WebSocket message into a dictionary."""
    try:
        value = __import__("json").loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _agent_display_details(agent_name: str) -> tuple[str, str]:
    """Resolve internal agent names to the human display name and team label used in handoff audio."""
    return AGENT_DISPLAY_DETAILS.get(agent_name, (agent_name, "support"))


def _handoff_intro(from_agent_name: str, to_agent_name: str) -> str:
    """Generate the receiving agent introduction spoken after a handoff."""
    from_display_name, _ = _agent_display_details(from_agent_name)
    to_display_name, to_team = _agent_display_details(to_agent_name)
    if to_agent_name == "supervisorAgent":
        return (
            f"Hi, this is {to_display_name}, the floor supervisor. "
            f"{from_display_name} asked me to step in and help sort this out."
        )
    return (
        f"Hi, this is {to_display_name} with {to_team}. "
        f"{from_display_name} asked me to step in and help."
    )


def _handoff_outro(from_agent_name: str, to_agent_name: str) -> str:
    """Generate the departing agent transfer line spoken before a handoff."""
    to_display_name, to_team = _agent_display_details(to_agent_name)
    if to_agent_name == "callcenteragent":
        return f"I'll bring {to_display_name} from our front desk back in now."
    if to_agent_name == "supervisorAgent":
        return "I'm sorry for the trouble. I'll bring in our floor supervisor to help with this."
    if to_agent_name == "humanEscalationAgent":
        return f"I'll connect you with {to_display_name} at our escalation desk now."
    return f"I'm sorry for the trouble. I'll transfer you to our {to_team} team so they can handle this."


def _agent_voice_id(agent_name: str, settings: Settings) -> str:
    """Select the configured ElevenLabs voice for the active agent."""
    agent_voice_ids = {
        "callcenteragent": settings.elevenlabs_voice_callcenter,
        "billingAgent": settings.elevenlabs_voice_billing,
        "technicalSupportAgent": settings.elevenlabs_voice_technical_support,
        "retentionAgent": settings.elevenlabs_voice_retention,
        "supervisorAgent": settings.elevenlabs_voice_supervisor,
        "humanEscalationAgent": settings.elevenlabs_voice_human_escalation,
    }
    return agent_voice_ids.get(agent_name) or settings.elevenlabs_voice_id


def _direct_handoff_agent_name(
    text: str,
    active_agent_name: str,
    is_verified: bool = True,
) -> str | None:
    """Apply deterministic keyword routing from the triage agent after verification."""
    if not is_verified:
        return None

    normalized = f" {text.lower()} "
    supervisor_terms = (
        " supervisor",
        " manager",
        " floor supervisor",
        " escalate to supervisor",
        " talk to supervisor",
        " speak to supervisor",
        " talk to a supervisor",
        " speak to a supervisor",
    )
    if active_agent_name != "supervisorAgent" and any(term in normalized for term in supervisor_terms):
        return "supervisorAgent"

    if active_agent_name != "callcenteragent":
        return None

    billing_terms = (
        " bill ",
        " billing ",
        " charge",
        " payment",
        " invoice",
        " fee",
        " fees",
        " credit",
        " expensive",
        " high this month",
        " why is my bill",
    )
    technical_terms = (
        " internet",
        " wifi",
        " wi-fi",
        " outage",
        " signal",
        " modem",
        " router",
        " dropping",
        " disconnect",
        " slow",
        " technician",
    )
    retention_terms = (
        " cancel",
        " cancellation",
        " downgrade",
        " retention",
        " leave",
        " switch provider",
        " too expensive",
        " cheaper plan",
    )
    if any(term in normalized for term in retention_terms):
        return "retentionAgent"
    if any(term in normalized for term in billing_terms):
        return "billingAgent"
    if any(term in normalized for term in technical_terms):
        return "technicalSupportAgent"
    return None


def _fixed_response_for_user_text(
    text: str,
    context: CallCenterContext,
    active_agent_name: str,
) -> str | None:
    """Return deterministic greetings, human-escalation replies, and call-closing responses before invoking the LLM."""
    normalized = " ".join(text.lower().strip().split())

    if _is_first_greeting(normalized, context, active_agent_name):
        context.greeted = True
        return "Thanks for calling Atenxion, this is Alice at the front desk. How can I help today?"

    if not context.greeted and active_agent_name == "callcenteragent":
        context.greeted = True

    if _is_human_escalation_request(normalized):
        return (
            "I understand. You can talk to a human supervisor at 09755083294. "
            "Thank you very much for calling Atenxion, and have a great rest of your day."
        )

    if _is_case_closing_confirmation(normalized):
        return "Thank you very much for calling Atenxion, and have a great rest of your day."

    return None


def _is_first_greeting(normalized: str, context: CallCenterContext, active_agent_name: str) -> bool:
    """Detect the initial greeting that should use the scripted front-desk opening."""
    if context.greeted or active_agent_name != "callcenteragent":
        return False
    return normalized in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}


def _is_human_escalation_request(normalized: str) -> bool:
    """Detect requests for a real human, not the simulated AI supervisor."""
    human_terms = (
        "human",
        "real person",
        "real agent",
        "live person",
        "live agent",
        "live representative",
        "representative",
        "human agent",
        "human representative",
    )
    return any(term in normalized for term in human_terms)


def _is_case_closing_confirmation(normalized: str) -> bool:
    """Detect user phrases that should close the call with a fixed goodbye."""
    closing_terms = (
        "case is closed",
        "case closed",
        "close the case",
        "mark as resolved",
        "mark it resolved",
        "it is resolved",
        "it's resolved",
        "issue is resolved",
        "that resolves it",
        "all set",
        "that's all",
        "that is all",
        "nothing else",
        "no more help",
        "no thanks",
        "no thank you",
    )
    return any(term in normalized for term in closing_terms)


def _should_skip_agent_sentence(
    sentence: str,
    active_agent_name: str,
    pending_handoff_agent_name: str | None,
) -> bool:
    """Filter streamed model sentences that duplicate backend-managed handoff wording."""
    return (
        _should_skip_handoff_sentence(sentence, pending_handoff_agent_name)
        or _should_skip_self_transfer_sentence(sentence, active_agent_name)
    )


def _should_skip_handoff_sentence(sentence: str, pending_handoff_agent_name: str | None) -> bool:
    """Suppress transfer/setup narration after the backend has already emitted handoff audio lines."""
    if not pending_handoff_agent_name:
        return False

    normalized = " ".join(sentence.lower().strip().strip("()").split())
    if not normalized:
        return True

    transfer_markers = (
        "transferred you",
        "i have transferred",
        "i've transferred",
        "i am transferring",
        "i'm transferring",
        "i will transfer",
        "i'll transfer",
        "i will connect",
        "i'll connect",
        "connect you to",
        "connect you with",
        "transfer you to",
        "transferring now",
        "active home internet service",
        "active services",
        "service info ready",
        "details ready",
        "account and service details",
        "thank you for your patience",
        "please hold",
        "i am a billing specialist",
        "i'm a billing specialist",
        "i am a technical support specialist",
        "i'm a technical support specialist",
        "i am a retention specialist",
        "i'm a retention specialist",
        "i am your billing specialist",
        "i am your technical support specialist",
        "will assist you with",
        "billing expert",
        "billing specialist",
        "technical support specialist",
        "won't need to repeat",
        "will not need to repeat",
    )
    return any(marker in normalized for marker in transfer_markers)


def _should_skip_self_transfer_sentence(sentence: str, active_agent_name: str) -> bool:
    """Suppress specialist sentences that claim to transfer to the same team already speaking."""
    normalized = " ".join(sentence.lower().strip().strip("()").split())
    if not normalized:
        return False

    self_transfer_markers = {
        "billingAgent": (
            "connect you to our billing",
            "connect you with our billing",
            "connecting you to our billing",
            "connecting you with our billing",
            "billing team for further assistance",
            "billing specialist for further assistance",
        ),
        "technicalSupportAgent": (
            "connect you to our technical support",
            "connect you with our technical support",
            "connecting you to our technical support",
            "connecting you with our technical support",
            "technical support team for further assistance",
            "technical support specialist for further assistance",
            "further assistance with your internet issue",
        ),
        "retentionAgent": (
            "connect you to our retention",
            "connect you with our retention",
            "connecting you to our retention",
            "connecting you with our retention",
            "retention team for further assistance",
            "retention specialist for further assistance",
        ),
    }
    return any(
        marker in normalized for marker in self_transfer_markers.get(active_agent_name, ())
    )


def _extract_text_delta(event: Any) -> str:
    """Extract assistant text deltas from raw OpenAI Agents SDK streaming events."""
    if getattr(event, "type", None) != "raw_response_event":
        return ""
    data = getattr(event, "data", None)
    data_type = getattr(data, "type", None)
    if data_type in {"response.output_text.delta", "response.text.delta"}:
        return str(getattr(data, "delta", "") or "")
    return ""


def _extract_tool_name(item: Any) -> str:
    """Read a tool name from the possible SDK stream item shapes."""
    raw = getattr(item, "raw_item", None)
    return (
        getattr(item, "name", None)
        or getattr(raw, "name", None)
        or getattr(getattr(raw, "function", None), "name", None)
        or "unknown_tool"
    )


def _extract_tool_arguments(item: Any) -> Any:
    """Read tool arguments from the possible SDK stream item shapes."""
    raw = getattr(item, "raw_item", None)
    return (
        getattr(item, "arguments", None)
        or getattr(raw, "arguments", None)
        or getattr(getattr(raw, "function", None), "arguments", None)
        or {}
    )


def _extract_tool_output(item: Any) -> Any:
    """Read tool output from the possible SDK stream item shapes."""
    return getattr(item, "output", None) or getattr(getattr(item, "raw_item", None), "output", None)
