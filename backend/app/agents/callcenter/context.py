"""Defines the mutable per-session state shared by agents and tools, including verification, active account, case data, and current agent."""
from dataclasses import dataclass, field


@dataclass
class CallCenterContext:
    """Per-session state object passed through OpenAI Agents SDK runs and tool calls."""
    session_id: str
    trace_id: str
    verified: bool = False
    greeted: bool = False
    current_agent_name: str | None = None
    active_account_id: str | None = None
    case_id: str | None = None
    case_notes: list[str] = field(default_factory=list)
