"""Contains tests for tool verification tests. in the backend."""
import json

import pytest

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.tools import get_latest_bill, lookup_customer_profile, verify_caller


class FakeToolContext:
    """Minimal stand-in for the SDK run context used to call tool functions in isolation."""
    def __init__(self, tool_name: str) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.context = CallCenterContext(session_id="test-session", trace_id="test-trace")
        self.tool_name = tool_name
        self.run_config = None


@pytest.mark.asyncio
async def test_unknown_phone_number_tells_agent_not_to_escalate() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await lookup_customer_profile.on_invoke_tool(
        FakeToolContext("lookup_customer_profile"),
        json.dumps({"phone_number": "00000000000"}),
    )

    assert result["found"] is False
    assert result["security_status"] == "account_not_found"
    assert "Do not transfer or escalate" in result["next_step"]
    assert "call back" in result["next_step"]


@pytest.mark.asyncio
async def test_failed_verification_tells_agent_not_to_escalate() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await verify_caller.on_invoke_tool(
        FakeToolContext("verify_caller"),
        json.dumps(
            {
                "phone_number": "09661200650",
                "date_of_birth": "1999-01-01",
                "pin_last4": "9999",
            }
        ),
    )

    assert result["verified"] is False
    assert result["security_status"] == "failed"
    assert "Do not transfer or escalate" in result["next_step"]
    assert "check their account details" in result["next_step"]


@pytest.mark.asyncio
async def test_account_specific_tools_require_verification() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await get_latest_bill.on_invoke_tool(
        FakeToolContext("get_latest_bill"),
        json.dumps({"account_id": "ATX-204871"}),
    )

    assert result["authorized"] is False
    assert result["security_status"] == "verification_required"
    assert "Do not provide account-specific details" in result["next_step"]


@pytest.mark.asyncio
async def test_account_specific_tools_allow_verified_context() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    ctx = FakeToolContext("get_latest_bill")
    ctx.context.verified = True

    result = await get_latest_bill.on_invoke_tool(
        ctx,
        json.dumps({"account_id": "ATX-204871"}),
    )

    assert result["requested_account_id"] == "ATX-204871"
    assert result["total_usd"] == 146.32
