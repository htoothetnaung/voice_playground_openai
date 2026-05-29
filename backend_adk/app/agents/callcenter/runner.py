"""Runs text turns through the Google ADK call-center agent graph with SQLite-backed session state."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai.types import Content, Part

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.graph import build_callcenter_agent_graph
from app.core.config import Settings

APP_NAME = "atenxion_callcenter_adk"
USER_ID = "callcenter-user"


def context_to_state(context: CallCenterContext) -> dict[str, Any]:
    """Convert the local dataclass context to ADK session state."""
    return {
        "session_id": context.session_id,
        "trace_id": context.trace_id,
        "verified": context.verified,
        "greeted": context.greeted,
        "current_agent_name": context.current_agent_name,
        "active_account_id": context.active_account_id,
        "case_id": context.case_id,
        "case_notes": list(context.case_notes),
    }


def state_to_context(context: CallCenterContext, state: dict[str, Any]) -> None:
    """Copy ADK session state back into the local dataclass used by routes and voice metrics."""
    context.verified = bool(state.get("verified", False))
    context.greeted = bool(state.get("greeted", False))
    context.current_agent_name = state.get("current_agent_name")
    context.active_account_id = state.get("active_account_id")
    context.case_id = state.get("case_id")
    context.case_notes = list(state.get("case_notes") or [])


def make_user_content(text: str) -> Content:
    """Build the Google GenAI content object expected by ADK Runner."""
    return Content(role="user", parts=[Part(text=text)])


def event_text(event: Any) -> str:
    """Extract text from the common ADK event content shape."""
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    text_parts = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            text_parts.append(str(text))
    return "".join(text_parts)


class CallCenterAdkEngine:
    """Small adapter around ADK Runner, session service, and call-center state mapping."""

    def __init__(self, settings: Settings, agent: Any | None = None) -> None:
        self.settings = settings
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is required to run backend_adk Google ADK/Gemini turns.")
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
        self.agent = agent or build_callcenter_agent_graph(model=settings.google_adk_model)
        self.session_db_path = Path(settings.adk_session_db_path)
        self.session_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_service = DatabaseSessionService(
            db_url=f"sqlite+aiosqlite:///{self.session_db_path.as_posix()}"
        )
        self.runner = Runner(
            agent=self.agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

    async def ensure_session(self, session_id: str, context: CallCenterContext) -> None:
        """Create the ADK session when needed and seed it with call-center state."""
        existing = await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
        )
        if existing is not None:
            state_to_context(context, existing.state)
            return
        await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
            state=context_to_state(context),
        )

    async def stream_turn(
        self,
        input_text: str,
        session_id: str,
        context: CallCenterContext,
    ) -> AsyncIterator[Any]:
        """Yield ADK events for one user turn."""
        await self.ensure_session(session_id, context)
        async for event in self.runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=make_user_content(input_text),
        ):
            yield event
        session = await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
        )
        if session is not None:
            state_to_context(context, session.state)


class CallCenterAdkRunner:
    """Text endpoint runner that owns the call-center ADK graph and persistent session service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = CallCenterAdkEngine(settings)

    async def run_turn(self, input_text: str, session_id: str | None = None) -> dict:
        """Run one user text turn with ADK Runner.run_async and expose selected context as trace data."""
        effective_session_id = session_id or f"callcenter-adk-{uuid4().hex}"
        trace_id = uuid4().hex
        context = CallCenterContext(
            session_id=effective_session_id,
            trace_id=trace_id,
            current_agent_name="callcenteragent",
        )
        final_output = ""
        async for event in self.engine.stream_turn(
            input_text=input_text,
            session_id=effective_session_id,
            context=context,
        ):
            text = event_text(event)
            if text:
                final_output = text
            is_final = getattr(event, "is_final_response", None)
            if callable(is_final) and is_final():
                final_output = text or final_output

        return {
            "session_id": effective_session_id,
            "final_output": final_output,
            "trace": {
                "trace_id": trace_id,
                "verified": context.verified,
                "active_account_id": context.active_account_id,
                "case_id": context.case_id,
                "case_notes": context.case_notes,
            },
        }
