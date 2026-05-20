"""Tests for the Atenxion Bank external API tool."""

import json

import httpx
import pytest

from app.agents.callcenter.bank_tool import (
    ATENXION_BANK_TOOL_DISPLAY_NAME,
    ATENXION_BANK_TRANSACTION_PATH,
    ATENXION_BANK_TOOL_NAME,
    fetch_atenxion_bank_transactions,
)
from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.tools import atenxion_bank_tool
from app.core.config import Settings


class FakeToolContext:
    """Minimal stand-in for the SDK run context used by isolated tool tests."""

    def __init__(self) -> None:
        self.context = CallCenterContext(session_id="test-session", trace_id="test-trace")
        self.tool_name = ATENXION_BANK_TOOL_NAME
        self.run_config = None


def _settings(**overrides) -> Settings:
    defaults = {
        "OPENAI_API_KEY": "sk-test",
        "ATENXION_BANK_API_BASE_URL": "https://api-qabank.atenxion.ai",
        "ATENXION_BANK_API_TOKEN": "bank-token",
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_atenxion_bank_client_posts_openapi_payload_and_normalizes_200() -> None:
    """The bank client follows the documented POST shape and returns compact latency metadata."""
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "txn-1",
                        "senderId": "6a0d6b143cac1525e1e4ce87",
                        "senderAccount": "1234",
                        "senderAccountType": "SAVINGS",
                        "amount": 100.5,
                        "transactionType": "LOCAL",
                        "transactionDate": "2025-01-15T10:30:00.000Z",
                        "remainingBalance": 4899.5,
                        "isCredit": False,
                    },
                    {
                        "id": "txn-2",
                        "senderId": "other",
                        "senderAccount": "9876",
                        "senderAccountType": "SAVINGS",
                        "amount": 25,
                        "transactionType": "LOCAL",
                        "transactionDate": "2025-01-16T10:30:00.000Z",
                        "remainingBalance": 4924.5,
                        "isCredit": True,
                    },
                ],
                "msg": "Success",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_atenxion_bank_transactions(
            _settings(),
            user_id="6a0d6b143cac1525e1e4ce87",
            client=client,
        )

    assert seen["url"] == f"https://api-qabank.atenxion.ai{ATENXION_BANK_TRANSACTION_PATH}"
    assert seen["authorization"] == "Bearer bank-token"
    assert seen["body"] == {"userId": "6a0d6b143cac1525e1e4ce87"}
    assert result["available"] is True
    assert result["tool_name"] == ATENXION_BANK_TOOL_NAME
    assert result["tool_display_name"] == ATENXION_BANK_TOOL_DISPLAY_NAME
    assert result["status_code"] == 200
    assert result["transaction_count"] == 2
    assert result["credit_count"] == 1
    assert result["debit_count"] == 1
    assert result["total_credit"] == 25
    assert result["total_debit"] == 100.5


@pytest.mark.asyncio
async def test_atenxion_bank_tool_requires_verified_context() -> None:
    """Bank transaction data is account-specific and must stay behind verification."""
    result = await atenxion_bank_tool.on_invoke_tool(
        FakeToolContext(),
        json.dumps({"user_id": "6a0d6b143cac1525e1e4ce87"}),
    )

    assert result["authorized"] is False
    assert result["security_status"] == "verification_required"


@pytest.mark.asyncio
async def test_atenxion_bank_tool_uses_shared_client_for_verified_context(monkeypatch) -> None:
    """The Agents SDK tool delegates to the shared bank API client after verification."""
    called: dict[str, str] = {}

    async def fake_fetch(settings: Settings, *, user_id: str, client=None) -> dict:
        called["user_id"] = user_id
        return {
            "available": True,
            "tool_name": ATENXION_BANK_TOOL_NAME,
            "tool_display_name": ATENXION_BANK_TOOL_DISPLAY_NAME,
            "status_code": 200,
            "user_id": user_id,
            "transaction_count": 1,
            "data": [{"id": "txn-1"}],
        }

    monkeypatch.setattr("app.agents.callcenter.tools.fetch_atenxion_bank_transactions", fake_fetch)
    ctx = FakeToolContext()
    ctx.context.verified = True

    result = await atenxion_bank_tool.on_invoke_tool(
        ctx,
        json.dumps({"user_id": "6a0d6b143cac1525e1e4ce87"}),
    )

    assert called["user_id"] == "6a0d6b143cac1525e1e4ce87"
    assert result["tool_name"] == ATENXION_BANK_TOOL_NAME
    assert result["tool_display_name"] == ATENXION_BANK_TOOL_DISPLAY_NAME
    assert result["status_code"] == 200
