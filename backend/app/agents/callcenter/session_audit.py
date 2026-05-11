"""MongoDB audit logging for call-center conversation sessions."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agents.callcenter.cascaded.events import serialize
from app.core.config import Settings, get_settings
from app.core.mongo import get_mongo_database

_UNSET = object()

def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for Mongo records."""
    return datetime.now(UTC)


class SessionAuditLogger:
    """Persist normalized session, event, and transcript data when MongoDB is available."""

    def __init__(self, settings: Settings | None = None, db: Any = _UNSET) -> None:
        self.settings = settings
        if db is not _UNSET:
            self.db = db
        else:
            self.settings = settings or get_settings()
            self.db = get_mongo_database(self.settings)

    @property
    def enabled(self) -> bool:
        return self.db is not None

    async def list_sessions(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent sessions with their latest ticket metadata for the admin console."""
        if self.db is None:
            return []
        try:
            cursor = self.db.sessions.find({}).sort("created_at", -1).limit(limit)
            sessions = await cursor.to_list(length=limit)
        except Exception:
            return []
        return [serialize(_without_id(session)) for session in sessions]

    async def session_detail(self, session_id: str) -> dict[str, Any] | None:
        """Return one session with transcript, events, and tickets for admin review."""
        if self.db is None:
            return None
        try:
            session = await self.db.sessions.find_one({"session_id": session_id})
            if not session:
                return None
            transcripts = await (
                self.db.session_transcripts.find({"session_id": session_id})
                .sort("updated_at", 1)
                .to_list(length=None)
            )
            events = await (
                self.db.session_events.find({"session_id": session_id})
                .sort("created_at", 1)
                .to_list(length=None)
            )
            tickets = await (
                self.db.session_tickets.find({"session_id": session_id})
                .sort("created_at", 1)
                .to_list(length=None)
            )
        except Exception:
            return None
        return serialize(
            {
                "session": _without_id(session),
                "transcripts": [_without_id(item) for item in transcripts],
                "events": [_without_id(item) for item in events],
                "tickets": [_without_id(item) for item in tickets],
            }
        )

    async def start_session(
        self,
        *,
        session_id: str,
        trace_id: str,
        architecture: str,
        starting_agent: str,
    ) -> None:
        if self.db is None:
            return
        now = utc_now()
        try:
            await self.db.sessions.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "session_id": session_id,
                        "trace_id": trace_id,
                        "architecture": architecture,
                        "starting_agent": starting_agent,
                        "status": "active",
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        except Exception:
            return

    async def record_event(
        self,
        session_id: str,
        event: dict[str, Any],
        *,
        direction: str = "server",
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None
        event_type = str(event.get("type") or "event")
        if event_type == "audio":
            return None
        document = {
            "session_id": session_id,
            "direction": direction,
            "event_name": event_type,
            "event_data": serialize(event),
            "created_at": utc_now(),
        }
        try:
            await self.db.session_events.insert_one(document)
        except Exception:
            return None
        if event_type in {"history_added", "history_updated"}:
            await self.record_transcript_payload(session_id, event)
        return await self.maybe_create_ticket_from_event(session_id, event)

    async def create_ticket(
        self,
        session_id: str,
        *,
        kind: str,
        title: str,
        summary: str,
        priority: str = "normal",
        source_event: dict[str, Any] | None = None,
        exclusive_outcome: bool = False,
    ) -> dict[str, Any] | None:
        """Create a ticket document for admin review and mark outcome tickets on the session."""
        if self.db is None:
            return None
        if exclusive_outcome:
            existing_outcome = await self._existing_outcome_ticket_kind(session_id)
            if existing_outcome is not None:
                return None
        now = utc_now()
        ticket = {
            "ticket_id": f"TKT-{uuid4().hex[:12].upper()}",
            "session_id": session_id,
            "kind": kind,
            "title": title,
            "summary": summary,
            "priority": priority,
            "status": "open" if kind != "resolved" else "closed",
            "source_event": serialize(source_event or {}),
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self.db.session_tickets.insert_one(ticket)
            session_update: dict[str, Any] = {
                "updated_at": now,
                "last_ticket_id": ticket["ticket_id"],
            }
            if exclusive_outcome:
                session_update["outcome_ticket_kind"] = kind
                session_update["outcome_ticket_id"] = ticket["ticket_id"]
            await self.db.sessions.update_one(
                {"session_id": session_id},
                {"$set": session_update},
                upsert=False,
            )
        except Exception:
            return None
        return serialize(_without_id(ticket))

    async def maybe_create_ticket_from_event(
        self,
        session_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Infer review tickets from normalized runtime events."""
        event_type = event.get("type")
        if event_type == "tool_end":
            tool_name = str(event.get("tool_name") or "")
            if tool_name == "schedule_technician":
                return await self.create_ticket(
                    session_id,
                    kind="field_service_action",
                    title="Technician visit scheduled",
                    summary="A technician scheduling tool completed during this conversation.",
                    priority="normal",
                    source_event=event,
                )
        if event_type != "history_added":
            return None
        item = event.get("item")
        if not isinstance(item, dict) or item.get("role") != "assistant":
            return None
        text = _extract_message_text(item.get("content") or []).lower()
        if "09755083294" in text or "human supervisor" in text:
            return await self.create_ticket(
                session_id,
                kind="needs_attention",
                title="Caller requested human attention",
                summary="The conversation ended with a human-supervisor handoff path.",
                priority="high",
                source_event=event,
                exclusive_outcome=True,
            )
        if "thank you very much for calling atenxion" in text or "thank you for calling atenxion" in text:
            return await self.create_ticket(
                session_id,
                kind="resolved",
                title="Issue resolved during call",
                summary="The session reached the closing statement and can be reviewed as resolved.",
                priority="low",
                source_event=event,
                exclusive_outcome=True,
            )
        return None

    async def record_transcript_payload(self, session_id: str, event: dict[str, Any]) -> None:
        if self.db is None:
            return
        if event.get("type") == "history_added":
            items = [event.get("item")]
        else:
            items = event.get("history") or []
        documents = []
        for item in items:
            transcript = _transcript_document(session_id, item)
            if transcript is not None:
                documents.append(transcript)
        for document in documents:
            try:
                await self.db.session_transcripts.update_one(
                    {"session_id": session_id, "item_id": document["item_id"]},
                    {"$set": document},
                    upsert=True,
                )
            except Exception:
                continue

    async def end_session(self, session_id: str, *, status: str = "ended") -> None:
        if self.db is None:
            return
        now = utc_now()
        try:
            if await self._existing_outcome_ticket_kind(session_id) is None:
                await self.create_ticket(
                    session_id,
                    kind="needs_attention",
                    title="Session ended without resolution",
                    summary="No resolved outcome was detected before the session ended.",
                    priority="normal",
                    exclusive_outcome=True,
                )
            await self.db.sessions.update_one(
                {"session_id": session_id},
                {"$set": {"status": status, "ended_at": now, "updated_at": now}},
                upsert=False,
            )
        except Exception:
            return

    async def _existing_outcome_ticket_kind(self, session_id: str) -> str | None:
        if self.db is None:
            return None
        try:
            session = await self.db.sessions.find_one({"session_id": session_id})
        except Exception:
            return None
        if not isinstance(session, dict):
            return None
        value = session.get("outcome_ticket_kind")
        return str(value) if value else None


class AuditedWebSocket:
    """Proxy a FastAPI WebSocket and persist JSON events sent to the client."""

    def __init__(self, websocket: Any, audit_logger: SessionAuditLogger, session_id: str) -> None:
        self.websocket = websocket
        self.audit_logger = audit_logger
        self.session_id = session_id

    async def receive(self) -> Any:
        return await self.websocket.receive()

    async def send_json(self, event: dict[str, Any]) -> None:
        await self.websocket.send_json(event)
        ticket = await self.audit_logger.record_event(self.session_id, event)
        if ticket is not None and event.get("type") != "ticket_created":
            ticket_event = {"type": "ticket_created", "ticket": ticket}
            await self.websocket.send_json(ticket_event)
            await self.audit_logger.record_event(self.session_id, ticket_event)

    async def close(self) -> None:
        await self.websocket.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.websocket, name)


def _transcript_document(session_id: str, item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict) or item.get("type") != "message":
        return None
    item_id = item.get("itemId") or item.get("item_id") or item.get("id")
    if not item_id:
        return None
    return {
        "session_id": session_id,
        "item_id": item_id,
        "role": item.get("role"),
        "text": _extract_message_text(item.get("content") or []),
        "item": serialize(item),
        "updated_at": utc_now(),
    }


def _extract_message_text(content: list[Any]) -> str:
    parts: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text") or entry.get("transcript")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _without_id(document: Any) -> Any:
    if isinstance(document, dict):
        return {key: value for key, value in document.items() if key != "_id"}
    return document
