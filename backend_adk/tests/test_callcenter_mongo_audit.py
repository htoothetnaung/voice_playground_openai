"""Tests for optional Mongo data fallback and session audit logging."""
from typing import Any

import pytest

from app.agents.callcenter.data_repository import CallCenterDataRepository, MOCK_DATA_COLLECTIONS
from app.agents.callcenter.mock_data import ATENXION_CUSTOMER_PROFILE, ATENXION_RAG_DOCUMENTS
from app.agents.callcenter.session_audit import SessionAuditLogger

try:
    from bson import ObjectId
except Exception:
    ObjectId = None


class FakeCollection:
    def __init__(self) -> None:
        self.updated: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
        self.inserted: list[dict[str, Any]] = []
        self.found: dict[str, Any] | None = None

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> None:
        self.updated.append((query, update, upsert))
        if self.found is not None and "$set" in update:
            self.found.update(update["$set"])

    async def insert_one(self, document: dict[str, Any]) -> None:
        if ObjectId is not None:
            document["_id"] = ObjectId()
        self.inserted.append(document)

    async def find_one(self, _query: dict[str, Any]) -> dict[str, Any] | None:
        return self.found


class FakeDb:
    def __init__(self) -> None:
        self.sessions = FakeCollection()
        self.sessions.found = {"session_id": "session-1"}
        self.session_events = FakeCollection()
        self.session_transcripts = FakeCollection()
        self.session_tickets = FakeCollection()
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, collection_name: str) -> FakeCollection:
        if collection_name not in self.collections:
            self.collections[collection_name] = FakeCollection()
        return self.collections[collection_name]


@pytest.mark.asyncio
async def test_mongo_repository_falls_back_to_mock_customer_profile() -> None:
    repository = CallCenterDataRepository(db=None)

    profile = await repository.customer_profile()

    assert profile["account_id"] == ATENXION_CUSTOMER_PROFILE["account_id"]
    assert profile["phone_number"] == ATENXION_CUSTOMER_PROFILE["phone_number"]


def test_rag_documents_are_additive_and_preserve_canonical_customer() -> None:
    assert ATENXION_CUSTOMER_PROFILE["account_id"] == "ATX-204871"
    assert ATENXION_CUSTOMER_PROFILE["phone_number"] == "09661200650"
    assert len(ATENXION_RAG_DOCUMENTS) == 1000
    assert "rag_documents" in MOCK_DATA_COLLECTIONS


@pytest.mark.asyncio
async def test_seed_mock_data_upserts_rag_documents_without_deleting_existing_records() -> None:
    db = FakeDb()
    repository = CallCenterDataRepository(db=db)

    seeded = await repository.seed_mock_data()

    assert seeded is True
    rag_collection = db.collections["rag_documents"]
    assert len(rag_collection.updated) == len(ATENXION_RAG_DOCUMENTS)
    first_query, first_update, first_upsert = rag_collection.updated[0]
    assert first_query == {"document_id": ATENXION_RAG_DOCUMENTS[0]["document_id"]}
    assert first_update["$set"]["document_id"] == ATENXION_RAG_DOCUMENTS[0]["document_id"]
    assert first_upsert is True
    assert rag_collection.inserted == []


@pytest.mark.asyncio
async def test_session_audit_writes_session_event_and_transcript_records() -> None:
    db = FakeDb()
    audit = SessionAuditLogger(db=db)

    await audit.start_session(
        session_id="session-1",
        trace_id="trace-1",
        architecture="cascaded_pipeline",
        starting_agent="callcenteragent",
    )
    await audit.record_event(
        "session-1",
        {
            "type": "history_added",
            "item": {
                "id": "item-1",
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "supervisor"}],
            },
        },
    )
    await audit.end_session("session-1")

    assert db.sessions.updated[0][0] == {"session_id": "session-1"}
    assert db.session_events.inserted[0]["event_name"] == "history_added"
    assert db.session_transcripts.updated[0][0] == {
        "session_id": "session-1",
        "item_id": "item-1",
    }
    assert db.session_transcripts.updated[0][1]["$set"]["text"] == "supervisor"


@pytest.mark.asyncio
async def test_session_audit_creates_exclusive_resolved_ticket() -> None:
    db = FakeDb()
    audit = SessionAuditLogger(db=db)

    ticket = await audit.record_event(
        "session-1",
        {
            "type": "history_added",
            "item": {
                "id": "assistant-1",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Thank you very much for calling Atenxion, and have a great rest of your day.",
                    }
                ],
            },
        },
    )

    assert ticket is not None
    assert ticket["kind"] == "resolved"
    assert "_id" not in ticket
    assert db.session_tickets.inserted[0]["status"] == "closed"
    assert db.sessions.found["outcome_ticket_kind"] == "resolved"


@pytest.mark.asyncio
async def test_session_audit_creates_attention_ticket_for_human_request() -> None:
    db = FakeDb()
    audit = SessionAuditLogger(db=db)

    ticket = await audit.record_event(
        "session-1",
        {
            "type": "history_added",
            "item": {
                "id": "assistant-2",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "You can talk to a human supervisor at 09755083294.",
                    }
                ],
            },
        },
    )

    assert ticket is not None
    assert ticket["kind"] == "needs_attention"
    assert ticket["priority"] == "high"


@pytest.mark.asyncio
async def test_session_audit_creates_field_service_ticket_for_technician_tool() -> None:
    db = FakeDb()
    audit = SessionAuditLogger(db=db)

    ticket = await audit.record_event(
        "session-1",
        {
            "type": "tool_end",
            "tool_name": "schedule_technician",
            "output": {"scheduled": True, "work_order_id": "WO-1"},
        },
    )

    assert ticket is not None
    assert ticket["kind"] == "field_service_action"
