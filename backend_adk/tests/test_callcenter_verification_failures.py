"""Contains tests for ADK tool verification behavior."""
import pytest

from app.agents.callcenter.tools import get_latest_bill, lookup_customer_profile, verify_caller


class FakeToolContext:
    """Minimal stand-in for ADK ToolContext used to call tool functions in isolation."""

    def __init__(self) -> None:
        self.state = {
            "session_id": "test-session",
            "trace_id": "test-trace",
            "verified": False,
            "case_notes": [],
        }


@pytest.mark.asyncio
async def test_unknown_phone_number_tells_agent_not_to_escalate() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await lookup_customer_profile(FakeToolContext(), "00000000000")

    assert result["found"] is False
    assert result["security_status"] == "account_not_found"
    assert "Do not transfer or escalate" in result["next_step"]
    assert "call back" in result["next_step"]


@pytest.mark.asyncio
async def test_failed_verification_tells_agent_not_to_escalate() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await verify_caller(
        FakeToolContext(),
        phone_number="09661200650",
        date_of_birth="1999-01-01",
        pin_last4="9999",
    )

    assert result["verified"] is False
    assert result["security_status"] == "failed"
    assert "Do not transfer or escalate" in result["next_step"]
    assert "check their account details" in result["next_step"]


@pytest.mark.asyncio
async def test_verification_accepts_equivalent_identity_formats() -> None:
    """Verify spoken or typed identity formats can still match the canonical mock record."""
    result = await verify_caller(
        FakeToolContext(),
        phone_number="09661200650",
        date_of_birth="29 May 2004",
        pin_last4="PIN: 1234",
    )

    assert result["verified"] is True
    assert result["security_status"] == "passed"
    assert result["account_id"] == "ATX-204871"


@pytest.mark.asyncio
async def test_lookup_customer_profile_accepts_formatted_phone_number() -> None:
    """Verify phone lookup ignores user-facing separators without changing account matching."""
    result = await lookup_customer_profile(FakeToolContext(), "096 612 00650")

    assert result["found"] is True
    assert result["profile"]["account_id"] == "ATX-204871"


@pytest.mark.asyncio
async def test_account_specific_tools_require_verification() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    result = await get_latest_bill(FakeToolContext(), "ATX-204871")

    assert result["authorized"] is False
    assert result["security_status"] == "verification_required"
    assert "Do not provide account-specific details" in result["next_step"]


@pytest.mark.asyncio
async def test_account_specific_tools_allow_verified_context() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    ctx = FakeToolContext()
    ctx.state["verified"] = True

    result = await get_latest_bill(ctx, "ATX-204871")

    assert result["requested_account_id"] == "ATX-204871"
    assert result["total_usd"] == 146.32
