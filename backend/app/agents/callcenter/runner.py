"""Runs one text turn through the call-center agent graph with SQLite-backed session memory and returns output plus trace context."""
from pathlib import Path
from uuid import uuid4

from agents import Runner, SQLiteSession

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.graph import build_callcenter_agent_graph
from app.core.config import Settings


class CallCenterRunner:
    """Text endpoint runner that owns the call-center Agent graph and SQLite session path."""
    def __init__(self, settings: Settings) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.settings = settings
        self.agent = build_callcenter_agent_graph(model=settings.responses_model)
        self.session_db_path = Path(settings.callcenter_session_db_path)
        self.session_db_path.parent.mkdir(parents=True, exist_ok=True)

    async def run_turn(self, input_text: str, session_id: str | None = None) -> dict:
        """Run one user text turn with OpenAI Agents SDK Runner.run and expose selected context as trace data."""
        effective_session_id = session_id or f"callcenter-{uuid4().hex}"
        trace_id = uuid4().hex
        context = CallCenterContext(
            session_id=effective_session_id,
            trace_id=trace_id,
        )
        session = SQLiteSession(effective_session_id, str(self.session_db_path))
        result = await Runner.run(
            self.agent,
            input=input_text,
            context=context,
            session=session,
        )
        return {
            "session_id": effective_session_id,
            "final_output": result.final_output,
            "trace": {
                "trace_id": trace_id,
                "verified": context.verified,
                "active_account_id": context.active_account_id,
                "case_id": context.case_id,
                "case_notes": context.case_notes,
            },
        }
