"""Tests for MCP-backed call-center workflow tools."""
import json

import pytest

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.tools import (
    create_customer_ticket_via_mcp,
    search_gmail_customer_history,
    send_customer_followup_email_via_mcp,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_mcp_config(monkeypatch: pytest.MonkeyPatch):
    """Keep these tests independent of any local MCP env configuration."""
    for name in (
        "MCP_GMAIL_OAUTH_TOKEN",
        "MCP_EMAIL_SERVER_URL",
        "MCP_EMAIL_AUTHORIZATION",
        "MCP_TICKETING_SERVER_URL",
        "MCP_TICKETING_AUTHORIZATION",
    ):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeToolContext:
    """Minimal stand-in for the SDK run context used to call tools in isolation."""

    def __init__(self, tool_name: str, verified: bool = True) -> None:
        self.context = CallCenterContext(session_id="test-session", trace_id="test-trace")
        self.context.verified = verified
        self.context.case_id = "CASE-ATX-204871-01"
        self.tool_name = tool_name
        self.run_config = None


@pytest.mark.asyncio
async def test_mcp_email_tool_requires_verified_context() -> None:
    result = await send_customer_followup_email_via_mcp.on_invoke_tool(
        FakeToolContext("send_customer_followup_email_via_mcp", verified=False),
        json.dumps(
            {
                "recipient_email": "alex.johnson@email.com",
                "subject": "Follow-up",
                "body": "Thanks for calling Atenxion.",
            }
        ),
    )

    assert result["authorized"] is False
    assert result["security_status"] == "verification_required"


@pytest.mark.asyncio
async def test_mcp_email_tool_reports_missing_remote_server() -> None:
    result = await send_customer_followup_email_via_mcp.on_invoke_tool(
        FakeToolContext("send_customer_followup_email_via_mcp"),
        json.dumps(
            {
                "recipient_email": "alex.johnson@email.com",
                "subject": "Follow-up",
                "body": "Thanks for calling Atenxion.",
            }
        ),
    )

    assert result["available"] is False
    assert "MCP_EMAIL_SERVER_URL" in result["reason"]
    assert "Gmail connector" in result["recommended_path"]


@pytest.mark.asyncio
async def test_mcp_gmail_tool_reports_missing_oauth_token() -> None:
    result = await search_gmail_customer_history.on_invoke_tool(
        FakeToolContext("search_gmail_customer_history"),
        json.dumps(
            {
                "customer_email": "alex.johnson@email.com",
                "query": "billing dispute",
            }
        ),
    )

    assert result["available"] is False
    assert "MCP_GMAIL_OAUTH_TOKEN" in result["reason"]
    assert "read/search" in result["doc_note"]


@pytest.mark.asyncio
async def test_mcp_ticket_tool_reports_missing_remote_server() -> None:
    result = await create_customer_ticket_via_mcp.on_invoke_tool(
        FakeToolContext("create_customer_ticket_via_mcp"),
        json.dumps(
            {
                "customer_identifier": "ATX-204871",
                "title": "Billing complaint",
                "complaint_summary": "Customer disputes roaming charges.",
                "priority": "high",
            }
        ),
    )

    assert result["available"] is False
    assert "MCP_TICKETING_SERVER_URL" in result["reason"]
    assert "Zendesk/Zoho Desk" in result["recommended_path"]
