"""Coordinates browser audio/text, Deepgram transcripts, Google ADK streamed LLM responses, ElevenLabs audio, handoff audio cues, history events, and metrics."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.agents.callcenter.cascaded.deepgram import (
    DeepgramStreamingTranscriber,
    TranscriptEvent,
)
from app.agents.callcenter.cascaded.elevenlabs_stt import ElevenLabsRealtimeTranscriber
from app.agents.callcenter.cascaded.elevenlabs import ElevenLabsTTSAdapter
from app.agents.callcenter.cascaded.events import audio_event, message_item, serialize
from app.agents.callcenter.cascaded.metrics import TurnMetrics
from app.agents.callcenter.cascaded.sentence_buffer import SentenceBuffer
from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.graph import build_callcenter_agent_map
from app.agents.callcenter.runner import CallCenterAdkEngine, event_text
from app.agents.callcenter.session_audit import AuditedWebSocket, SessionAuditLogger
from app.core.config import Settings

HANDOFF_TRANSFER_DELAY_SECONDS = 2.5
MAX_AGENT_TURNS = 30
PCM_BYTES_PER_SAMPLE = 2
MIN_TTS_AUDIO_FRAME_MS = 40
STT_FINAL_FALLBACK_MS = 900
logger = logging.getLogger(__name__)

AGENT_DISPLAY_DETAILS = {
    "callcenteragent": ("Alice", "front desk"),
    "billingAgent": ("Austin", "billing"),
    "technicalSupportAgent": ("Bob", "technical support"),
    "retentionAgent": ("Maya", "retention"),
    "supervisorAgent": ("Sarah", "floor supervisor"),
    "humanEscalationAgent": ("Jordan", "escalation desk"),
}

HANDOFF_OUTRO_TEMPLATES = {
    "callcenteragent": (
        "I'll bring {to_display_name} from our front desk back in now.",
        "Let me bring {to_display_name} at the front desk back in.",
        "I'll route you back to {to_display_name} at the front desk.",
    ),
    "supervisorAgent": (
        "Hang tight while I bring in our floor supervisor.",
        "I'll bring our floor supervisor in now to help with this.",
        "Let me get our floor supervisor on the line.",
    ),
    "humanEscalationAgent": (
        "I'll connect you with {to_display_name} at our escalation desk now.",
        "Hang tight while I bring {to_display_name} from escalation in.",
        "Let me get {to_display_name} at our escalation desk on the line.",
    ),
    "default": (
        "Hang tight while I bring in our {to_team} team.",
        "I'll get our {to_team} team on the line now.",
        "Let me bring in someone from {to_team} to take it from here.",
    ),
}

HANDOFF_INTRO_TEMPLATES = {
    "callcenteragent": (
        "Hi, this is {to_display_name} at the front desk. I can help from here.",
        "This is {to_display_name} at the front desk. I'll take it from here.",
        "Hi, {to_display_name} here at the front desk. Let me pick this back up.",
    ),
    "supervisorAgent": (
        "Hi, this is {to_display_name}, the floor supervisor. I can help from here.",
        "This is {to_display_name}, the floor supervisor. I'll take it from here.",
        "Hi, {to_display_name} here from the floor supervisor desk. Let's sort this out.",
    ),
    "default": (
        "Hi, this is {to_display_name} with {to_team}. I can help from here.",
        "This is {to_display_name} in {to_team}. I'll take it from here.",
        "Hi, {to_display_name} here from {to_team}. Let me take a look.",
    ),
}


class CallCenterAdkCascadedRuntime:
    """Runtime that coordinates Deepgram STT, Google ADK streaming, ElevenLabs TTS, and frontend WebSocket events."""
    architecture = "cascaded_pipeline"

    def __init__(
        self,
        settings: Settings,
        transcriber: Any | None = None,
        tts_adapter: ElevenLabsTTSAdapter | None = None,
        architecture: str = "cascaded_pipeline",
    ) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings
        self.architecture = architecture
        self.agents = build_callcenter_agent_map(model=settings.google_adk_model)
        self.adk_engines = {
            name: CallCenterAdkEngine(settings, agent=agent)
            for name, agent in self.agents.items()
        }
        self.transcriber = transcriber
        self.tts_adapter = tts_adapter
        self._active_stt_metrics: TurnMetrics | None = None
        self._response_task: asyncio.Task[None] | None = None
        self._ptt_audio_buffer: bytearray | None = None
        self._client_speech_gate_open = False
        self._gated_audio_active = False

    async def serve(self, websocket: WebSocket, agent_name: str | None = None) -> None:
        """Own the lifetime of one WebSocket session, initialize provider or SDK state, and coordinate reader and writer tasks."""
        await websocket.accept()

        starting_agent_name = agent_name or "callcenteragent"
        starting_agent = self.agents.get(starting_agent_name, self.agents["callcenteragent"])
        effective_session_id = f"callcenter-cascaded-{uuid4().hex}"
        trace_id = uuid4().hex
        context = CallCenterContext(session_id=effective_session_id, trace_id=trace_id)
        context.current_agent_name = starting_agent.name
        adk_session_id = effective_session_id
        await self.adk_engines[starting_agent.name].ensure_session(adk_session_id, context)
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
                    await audited_websocket.send_json(
                        {
                            "type": "stt_stream_ready",
                            "stt_model": self._stt_model_name(),
                            "stt_provider": self._stt_provider_name(),
                        }
                    )
                except Exception as exc:
                    await audited_websocket.send_json(
                        {
                            "type": "error",
                            "error": f"{self._stt_display_name()} live STT connection failed; push-to-talk transcription will still retry: {exc}",
                        }
                    )
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
                    "stt_model": self._stt_model_name(),
                    "stt_provider": self._stt_provider_name(),
                    "llm_model": self.settings.google_adk_model,
                    "tts_model": self.settings.elevenlabs_tts_model,
                }
            )

            consumer_task = asyncio.create_task(
                self._consume_client(audited_websocket, transcriber, starting_agent, context, adk_session_id, tts_adapter)
            )
            if transcriber is not None:
                transcript_task = asyncio.create_task(
                    self._consume_transcripts(audited_websocket, transcriber, starting_agent, context, adk_session_id, tts_adapter)
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

    def _build_transcriber(self) -> Any | None:
        """Create the configured realtime STT adapter when credentials are available."""
        if self.architecture == "elevenlabs_pipeline":
            if not self.settings.elevenlabs_api_key:
                return None
            return ElevenLabsRealtimeTranscriber(
                api_key=self.settings.elevenlabs_api_key,
                model=self.settings.elevenlabs_stt_model,
                sample_rate=self.settings.elevenlabs_stt_sample_rate,
                commit_strategy=self.settings.elevenlabs_stt_commit_strategy,
                vad_silence_threshold_secs=self.settings.elevenlabs_stt_vad_silence_threshold_secs,
                vad_threshold=self.settings.elevenlabs_stt_vad_threshold,
                min_speech_duration_ms=self.settings.elevenlabs_stt_min_speech_duration_ms,
                min_silence_duration_ms=self.settings.elevenlabs_stt_min_silence_duration_ms,
                open_timeout_seconds=self.settings.cascaded_provider_timeout_seconds,
            )
        if not self.settings.deepgram_api_key:
            return None
        return DeepgramStreamingTranscriber(
            api_key=self.settings.deepgram_api_key,
            model=self.settings.deepgram_stt_model,
            sample_rate=self.settings.cascaded_input_sample_rate,
            endpointing_ms=self.settings.deepgram_endpointing_ms,
            utterance_end_ms=self.settings.deepgram_utterance_end_ms,
            open_timeout_seconds=self.settings.cascaded_provider_timeout_seconds,
        )

    def _stt_provider_name(self) -> str:
        return "elevenlabs" if self.architecture == "elevenlabs_pipeline" else "deepgram"

    def _stt_model_name(self) -> str:
        if self.architecture == "elevenlabs_pipeline":
            return self.settings.elevenlabs_stt_model
        return self.settings.deepgram_stt_model

    def _stt_display_name(self) -> str:
        return "ElevenLabs Scribe" if self.architecture == "elevenlabs_pipeline" else "Deepgram"

    def _stt_commit_silence_ms(self) -> int:
        if self.architecture == "elevenlabs_pipeline":
            return self.settings.elevenlabs_stt_commit_silence_ms
        return self.settings.deepgram_endpointing_ms

    def _stt_input_sample_rate(self) -> int:
        if self.architecture == "elevenlabs_pipeline":
            return self.settings.elevenlabs_stt_sample_rate
        return self.settings.cascaded_input_sample_rate

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
        transcriber: Any | None,
        starting_agent: Any,
        context: CallCenterContext,
        session: str,
        tts_adapter: ElevenLabsTTSAdapter | None,
    ) -> None:
        """Read frontend WebSocket input and forward audio, text, interrupt, commit, and ping messages to the active session."""
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()

            if message.get("bytes") is not None:
                self._gated_audio_active = self._client_speech_gate_open or self._ptt_audio_buffer is not None
                if self._active_stt_metrics is None:
                    self._active_stt_metrics = self._new_metrics()
                first_audio_chunk = self._active_stt_metrics.user_audio_bytes == 0
                self._active_stt_metrics.user_audio_bytes += len(message["bytes"])
                if self._ptt_audio_buffer is not None:
                    self._ptt_audio_buffer.extend(message["bytes"])
                if first_audio_chunk:
                    await websocket.send_json(
                        {
                            "type": "stt_audio_received",
                            "bytes": len(message["bytes"]),
                            "stt_model": self._stt_model_name(),
                            "stt_provider": self._stt_provider_name(),
                        }
                    )
                if self._ptt_audio_buffer is not None:
                    continue
                if transcriber is not None:
                    try:
                        await transcriber.send_audio(message["bytes"])
                    except Exception as exc:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": f"{self._stt_display_name()} STT stream unavailable: {exc}",
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
                client_payload = payload.get("event", {}).get("payload")
                if isinstance(client_payload, dict):
                    client_event_type = client_payload.get("type")
                    if client_event_type == "input_audio_buffer.clear":
                        self._ptt_audio_buffer = bytearray()
                        self._gated_audio_active = True
                    elif client_event_type == "speech_gate.open":
                        self._client_speech_gate_open = True
                        self._gated_audio_active = True
                        if self._response_task and not self._response_task.done():
                            self._response_task.cancel()
                            await websocket.send_json({"type": "audio_interrupted"})
                    elif client_event_type == "speech_gate.closed":
                        self._client_speech_gate_open = False
                        self._gated_audio_active = False
            elif message_type == "audio_commit" and transcriber is not None:
                if self._ptt_audio_buffer is not None:
                    await self._commit_ptt_audio(
                        websocket,
                        transcriber,
                        starting_agent,
                        context,
                        session,
                        tts_adapter,
                    )
                else:
                    await transcriber.flush_audio(duration_ms=self._stt_commit_silence_ms())
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})

    async def _commit_ptt_audio(
        self,
        websocket: WebSocket,
        transcriber: Any,
        starting_agent: Any,
        context: CallCenterContext,
        session: str,
        tts_adapter: ElevenLabsTTSAdapter | None,
    ) -> None:
        """Transcribe one push-to-talk clip and start the agent turn."""
        audio = bytes(self._ptt_audio_buffer or b"")
        self._ptt_audio_buffer = None
        metrics = self._active_stt_metrics or self._new_metrics()
        self._active_stt_metrics = None
        if not audio:
            return

        try:
            text = await transcriber.transcribe_pcm(audio)
        except Exception as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": f"{self._stt_display_name()} PTT transcription failed: {exc}",
                }
            )
            return

        await websocket.send_json(
            {
                "type": "stt_final",
                "text": text,
                "is_final": True,
                "speech_final": True,
            }
        )
        if not text:
            return

        metrics.turn_detected_ms = metrics.mark_ms()
        await websocket.send_json({"type": "turn_detected", "text": text})
        await self._start_agent_turn(
            websocket,
            text=text,
            starting_agent=starting_agent,
            context=context,
            session=session,
            tts_adapter=tts_adapter,
            metrics=metrics,
        )

    async def _consume_transcripts(
        self,
        websocket: WebSocket,
        transcriber: Any,
        starting_agent: Any,
        context: CallCenterContext,
        session: str,
        tts_adapter: ElevenLabsTTSAdapter | None,
    ) -> None:
        """Consume STT transcript events and start an ADK agent turn when speech finalizes."""
        pending_final_task: asyncio.Task[None] | None = None

        async def start_turn(event: TranscriptEvent, metrics: TurnMetrics) -> None:
            text = event.text.strip()
            if not text:
                return
            metrics.turn_detected_ms = metrics.mark_ms()
            await websocket.send_json({"type": "turn_detected", "text": text})
            self._active_stt_metrics = None
            await self._start_agent_turn(
                websocket,
                text=text,
                starting_agent=starting_agent,
                context=context,
                session=session,
                tts_adapter=tts_adapter,
                metrics=metrics,
            )

        async def start_turn_after_endpoint_timeout(
            event: TranscriptEvent,
            metrics: TurnMetrics,
        ) -> None:
            await asyncio.sleep(STT_FINAL_FALLBACK_MS / 1000)
            flushed = transcriber.aggregator.flush()
            await start_turn(flushed or event, metrics)

        def cancel_pending_final() -> None:
            nonlocal pending_final_task
            if pending_final_task and not pending_final_task.done():
                pending_final_task.cancel()
            pending_final_task = None

        try:
            while True:
                event = await transcriber.events.get()
                metrics = self._active_stt_metrics or self._new_metrics()
                if event.event_type == "speech_started":
                    cancel_pending_final()
                    if self._response_task and not self._response_task.done():
                        self._response_task.cancel()
                        await websocket.send_json({"type": "audio_interrupted"})
                    await websocket.send_json({"type": "speech_started"})
                    continue

                if event.event_type == "stt_partial":
                    cancel_pending_final()
                    if metrics.stt_first_partial_ms is None:
                        metrics.stt_first_partial_ms = metrics.mark_ms()
                    await websocket.send_json({"type": "stt_partial", "text": event.text, "raw": event.raw})
                    continue

                if event.event_type == "stt_final":
                    cancel_pending_final()
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
                    if event.speech_final:
                        await start_turn(event, metrics)
                        continue

                    pending_final_task = asyncio.create_task(
                        start_turn_after_endpoint_timeout(event, metrics)
                    )
        finally:
            cancel_pending_final()

    async def _start_agent_turn(
        self,
        websocket: WebSocket,
        text: str,
        starting_agent: Any,
        context: CallCenterContext,
        session: str,
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
        session: str,
        tts_adapter: ElevenLabsTTSAdapter | None,
        metrics: TurnMetrics,
    ) -> None:
        """Stream one Google ADK turn, manage handoffs, queue sentences for TTS, and emit final history and metrics."""
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

                engine = self.adk_engines.get(active_agent_name) or self.adk_engines[starting_agent.name]
                async for event in engine.stream_turn(
                    input_text=text,
                    session_id=session,
                    context=context,
                ):
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

                    new_agent_name = _extract_transfer_agent_name(event)
                    if new_agent_name:
                        if new_agent_name != active_agent_name:
                            previous_agent_name = active_agent_name
                            display_name, team = _agent_display_details(new_agent_name)
                            pre_handoff_remaining = sentence_buffer.flush()
                            if pre_handoff_remaining and not _should_skip_pre_handoff_sentence(
                                pre_handoff_remaining,
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
            logger.exception("Cascaded voice turn failed")
            tts_worker.cancel()
            await websocket.send_json(
                {
                    "type": "error",
                    "error": f"cascaded_turn_failed: {_format_exception(exc)}",
                }
            )

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
            try:
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
            except Exception as exc:
                logger.warning("TTS sentence synthesis failed: %s", _format_exception(exc), exc_info=True)
                await websocket.send_json(
                    {
                        "type": "tts_error",
                        "agent_name": agent_name,
                        "error": _format_exception(exc),
                    }
                )
                continue

            if len(pending_audio) >= PCM_BYTES_PER_SAMPLE:
                emit_length = len(pending_audio) - (len(pending_audio) % PCM_BYTES_PER_SAMPLE)
                audio_bytes = pending_audio[:emit_length]
                metrics.output_audio_bytes += len(audio_bytes)
                await websocket.send_json(audio_event(assistant_item_id, 0, audio_bytes, agent_name=agent_name))

    async def _send_run_item_event(self, websocket: WebSocket, event: Any, active_agent_name: str) -> None:
        """Translate Google ADK tool-call stream events into frontend tool_start/tool_end events."""
        function_call = _extract_adk_function_call(event)
        if function_call is not None:
            await websocket.send_json(
                {
                    "type": "tool_start",
                    "agent_name": active_agent_name,
                    "tool_name": _extract_function_name(function_call),
                    "arguments": _extract_function_args(function_call),
                }
            )
            return

        function_response = _extract_adk_function_response(event)
        if function_response is not None:
            await websocket.send_json(
                {
                    "type": "tool_end",
                    "agent_name": active_agent_name,
                    "tool_name": _extract_function_name(function_response),
                    "arguments": {},
                    "output": serialize(_extract_function_response(function_response)),
                }
            )
            return

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
            stt_provider=self._stt_provider_name(),
            stt_model=self._stt_model_name(),
            llm_provider="google_adk",
            llm_model=self.settings.google_adk_model,
            tts_provider="elevenlabs",
            tts_model=self.settings.elevenlabs_tts_model,
            tts_voice_id=self.settings.elevenlabs_voice_id,
            input_sample_rate=self._stt_input_sample_rate(),
            output_sample_rate=self.settings.cascaded_output_sample_rate,
        )


def _loads(text: str) -> dict[str, Any]:
    """Safely parse a frontend text WebSocket message into a dictionary."""
    try:
        value = __import__("json").loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _format_exception(exc: BaseException) -> str:
    """Return a useful exception string even for errors such as TimeoutError with empty messages."""
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return repr(exc)


def _agent_display_details(agent_name: str) -> tuple[str, str]:
    """Resolve internal agent names to the human display name and team label used in handoff audio."""
    return AGENT_DISPLAY_DETAILS.get(agent_name, (agent_name, "support"))


def _handoff_template_index(from_agent_name: str, to_agent_name: str, template_count: int) -> int:
    """Pick a stable phrase variant without relying on Python's randomized hash seed."""
    if template_count <= 1:
        return 0
    key = f"{from_agent_name}->{to_agent_name}"
    return sum(ord(character) for character in key) % template_count


def _handoff_intro(from_agent_name: str, to_agent_name: str) -> str:
    """Generate the receiving agent introduction spoken after a handoff."""
    to_display_name, to_team = _agent_display_details(to_agent_name)
    templates = HANDOFF_INTRO_TEMPLATES.get(
        to_agent_name,
        HANDOFF_INTRO_TEMPLATES["default"],
    )
    template = templates[_handoff_template_index(from_agent_name, to_agent_name, len(templates))]
    return template.format(to_display_name=to_display_name, to_team=to_team)


def _handoff_outro(from_agent_name: str, to_agent_name: str) -> str:
    """Generate the departing agent transfer line spoken before a handoff."""
    to_display_name, to_team = _agent_display_details(to_agent_name)
    templates = HANDOFF_OUTRO_TEMPLATES.get(
        to_agent_name,
        HANDOFF_OUTRO_TEMPLATES["default"],
    )
    template = templates[_handoff_template_index(from_agent_name, to_agent_name, len(templates))]
    return template.format(to_display_name=to_display_name, to_team=to_team)


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
        " cancel my",
        " cancel service",
        " cancel the service",
        " cancel my service",
        " cancel account",
        " cancel my account",
        " close account",
        " close my account",
        " terminate",
        " downgrade",
        " retention",
        " retention agent",
        " retention specialist",
        " transfer me to retention",
        " transfer to retention",
        " leave",
        " switch provider",
        " too expensive",
        " cheaper plan",
    )
    if active_agent_name != "retentionAgent" and any(term in normalized for term in retention_terms):
        return "retentionAgent"

    if active_agent_name != "callcenteragent":
        return None

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


def _should_skip_pre_handoff_sentence(sentence: str, pending_handoff_agent_name: str | None) -> bool:
    """Suppress verbose setup text that would delay the backend-managed transfer cue."""
    if not pending_handoff_agent_name:
        return False
    if _should_skip_handoff_sentence(sentence, pending_handoff_agent_name):
        return True

    normalized = " ".join(sentence.lower().strip().strip("()").split())
    if not normalized:
        return True

    summary_markers = (
        "i have verified your account",
        "i've verified your account",
        "i verified your account",
        "i have confirmed your account",
        "i can see you have",
        "i see you have",
        "you have three active services",
        "you have active services",
        "active services:",
        "5g mobile",
        "unlimited plus plan",
        "tablet data",
        "home internet",
        "1 gig speed",
        "the next agent",
        "another agent",
        "so they can handle",
        "they can handle",
        "they'll handle",
        "who can handle",
        "who will help",
        "will review",
        "can review",
    )
    if any(marker in normalized for marker in summary_markers):
        return True

    return len(normalized) > 180 and any(
        marker in normalized
        for marker in (
            "account",
            "service",
            "plan",
            "bill",
            "billing",
            "charges",
            "transfer",
            "team",
        )
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
        "account summary",
        "account details",
        "service summary",
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
        "retention specialist",
        "floor supervisor",
        "step in and help",
        "take over from here",
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
            "connect you to our payment",
            "connect you with our payment",
            "connecting you to our payment",
            "connecting you with our payment",
            "connect you now to our payment",
            "connecting you now to our payment",
            "billing team for further assistance",
            "billing specialist for further assistance",
            "payment specialist who can assist",
            "payment specialist for further assistance",
            "billing and payment",
        ),
        "technicalSupportAgent": (
            "connect you to our technical support",
            "connect you with our technical support",
            "connecting you to our technical support",
            "connecting you with our technical support",
            "connect you to our network",
            "connect you with our network",
            "connecting you to our network",
            "connecting you with our network",
            "technical support team for further assistance",
            "technical support specialist for further assistance",
            "network specialist who can assist",
            "network specialist for further assistance",
            "further assistance with your internet issue",
        ),
        "retentionAgent": (
            "connect you to our retention",
            "connect you with our retention",
            "connecting you to our retention",
            "connecting you with our retention",
            "connect you to our cancellation",
            "connect you with our cancellation",
            "connecting you to our cancellation",
            "connecting you with our cancellation",
            "retention team for further assistance",
            "retention specialist for further assistance",
            "cancellation specialist who can assist",
            "cancellation specialist for further assistance",
            "save specialist who can assist",
            "save specialist for further assistance",
        ),
        "supervisorAgent": (
            "connect you to our supervisor",
            "connect you with our supervisor",
            "connecting you to our supervisor",
            "connecting you with our supervisor",
            "floor supervisor for further assistance",
            "supervisor who can assist",
        ),
        "humanEscalationAgent": (
            "connect you to our escalation",
            "connect you with our escalation",
            "connecting you to our escalation",
            "connecting you with our escalation",
            "escalation specialist for further assistance",
            "escalation desk for further assistance",
        ),
    }
    return any(
        marker in normalized for marker in self_transfer_markers.get(active_agent_name, ())
    )


def _extract_text_delta(event: Any) -> str:
    """Extract assistant text deltas from Google ADK or legacy test event shapes."""
    text = event_text(event)
    if text:
        return text
    if getattr(event, "type", None) != "raw_response_event":
        return ""
    data = getattr(event, "data", None)
    data_type = getattr(data, "type", None)
    if data_type in {"response.output_text.delta", "response.text.delta"}:
        return str(getattr(data, "delta", "") or "")
    return ""


def _event_parts(event: Any) -> list[Any]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _extract_adk_function_call(event: Any) -> Any | None:
    for part in _event_parts(event):
        function_call = getattr(part, "function_call", None)
        if function_call is not None:
            return function_call
    return None


def _extract_adk_function_response(event: Any) -> Any | None:
    for part in _event_parts(event):
        function_response = getattr(part, "function_response", None)
        if function_response is not None:
            return function_response
    return None


def _extract_transfer_agent_name(event: Any) -> str | None:
    function_call = _extract_adk_function_call(event)
    if function_call is None:
        return None
    if _extract_function_name(function_call) not in {"transfer_to_agent", "transferToAgent"}:
        return None
    args = _extract_function_args(function_call)
    if isinstance(args, dict):
        agent_name = args.get("agent_name") or args.get("agentName")
        return str(agent_name) if agent_name else None
    return None


def _extract_function_name(value: Any) -> str:
    return str(getattr(value, "name", None) or getattr(value, "function_name", None) or "unknown_tool")


def _extract_function_args(value: Any) -> Any:
    args = getattr(value, "args", None)
    if args is not None:
        return args
    return getattr(value, "arguments", None) or {}


def _extract_function_response(value: Any) -> Any:
    response = getattr(value, "response", None)
    if response is not None:
        return response
    return getattr(value, "result", None) or {}


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
