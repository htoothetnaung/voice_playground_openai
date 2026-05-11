"""Implements account lookup, verification, billing, technical support, retention, supervisor, and case-management tool behavior over mock data."""
from agents import RunContextWrapper, function_tool

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.data_repository import CallCenterDataRepository


def create_case_id(prefix: str) -> str:
    """Create deterministic demo case or work-order identifiers tied to the mock Atenxion account."""
    return f"{prefix}-ATX-204871-01"


def _repository() -> CallCenterDataRepository:
    """Create the data repository used by async tool functions."""
    return CallCenterDataRepository()


def _verification_required() -> dict:
    """Return the standard tool response that prevents account-specific data before caller verification."""
    return {
        "authorized": False,
        "security_status": "verification_required",
        "next_step": (
            "Do not provide account-specific details yet. Ask the caller to verify the phone number, "
            "date of birth, and 4-digit PIN first."
        ),
    }


def _is_verified(ctx: RunContextWrapper[CallCenterContext]) -> bool:
    """Read the SDK run context to determine whether account-specific tools may proceed."""
    return bool(ctx.context.verified)


@function_tool
async def lookup_customer_profile(
    ctx: RunContextWrapper[CallCenterContext],
    phone_number: str,
) -> dict:
    """Look up the Atenxion customer profile by phone number."""
    customer_profile = await _repository().customer_profile()
    matched = phone_number == customer_profile["phone_number"]
    if matched:
        ctx.context.active_account_id = customer_profile["account_id"]
        return {
            "found": True,
            "profile": {
                "account_id": customer_profile["account_id"],
                "full_name": customer_profile["full_name"],
                "phone_number": customer_profile["phone_number"],
                "service_address": customer_profile["service_address"],
                "current_plan": customer_profile["current_plan"],
                "sentiment": customer_profile["sentiment"],
            },
        }
    return {
        "found": False,
        "security_status": "account_not_found",
        "next_step": (
            "Do not transfer or escalate. Tell the caller there is no customer profile matching "
            "that phone number in Atenxion's records. Ask them to check their account details "
            "and call back, then close the call politely."
        ),
    }


@function_tool
async def verify_caller(
    ctx: RunContextWrapper[CallCenterContext],
    phone_number: str,
    date_of_birth: str,
    pin_last4: str,
) -> dict:
    """Verify the caller using phone number, date of birth, and 4-digit PIN."""
    customer_profile = await _repository().customer_profile()
    verified = (
        phone_number == customer_profile["phone_number"]
        and date_of_birth == customer_profile["date_of_birth"]
        and pin_last4 == customer_profile["pin_last4"]
    )
    ctx.context.verified = verified
    if verified:
        ctx.context.active_account_id = customer_profile["account_id"]
        return {
            "verified": True,
            "account_id": customer_profile["account_id"],
            "security_status": "passed",
        }
    return {
        "verified": False,
        "security_status": "failed",
        "next_step": (
            "Do not transfer or escalate. Tell the caller the phone number, date of birth, "
            "or PIN does not match Atenxion's records. Ask them to check their account details "
            "and call back, then close the call politely."
        ),
    }


@function_tool
async def lookup_active_services(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
) -> dict:
    """Return the active Atenxion services on an account."""
    if not _is_verified(ctx):
        return _verification_required()
    active_services = await _repository().active_services()
    return {
        "requested_account_id": account_id,
        "services": active_services["services"],
    }


@function_tool
async def create_case(
    ctx: RunContextWrapper[CallCenterContext],
    reason: str,
    priority: str,
    owning_team: str,
) -> dict:
    """Create a support case with a team owner and priority."""
    if not _is_verified(ctx):
        return _verification_required()
    case_id = create_case_id("CASE")
    ctx.context.case_id = case_id
    return {
        "case_id": case_id,
        "status": "open",
        "reason": reason,
        "priority": priority,
        "owning_team": owning_team,
    }


@function_tool
async def add_case_note(
    ctx: RunContextWrapper[CallCenterContext],
    case_id: str,
    note: str,
    visibility: str,
) -> dict:
    """Attach an internal case note to an existing support case."""
    if not _is_verified(ctx):
        return _verification_required()
    ctx.context.case_notes.append(note)
    return {
        "case_id": case_id,
        "saved": True,
        "note_preview": note[:140],
        "visibility": visibility,
    }


@function_tool
async def get_latest_bill(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
) -> dict:
    """Fetch the latest Atenxion bill for an account."""
    if not _is_verified(ctx):
        return _verification_required()
    latest_bill = await _repository().latest_bill()
    return {
        "requested_account_id": account_id,
        **latest_bill,
    }


@function_tool
async def explain_charge_breakdown(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    bill_id: str,
) -> dict:
    """Explain the bill line items in plain language."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "bill_id": bill_id,
        "explanation": [
            "The bill increased mainly because of international calls and two roaming day passes.",
            "The base plan stayed the same month over month.",
            "Device protection and taxes were consistent with the prior bill.",
        ],
        "driver_summary": "Usage-based travel charges caused most of the increase.",
    }


@function_tool
async def offer_payment_arrangement(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    hardship_reason: str,
) -> dict:
    """Offer an eligible short-term payment arrangement."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "eligible": True,
        "offer": {
            "deferred_amount_usd": 60,
            "deferred_until": "2026-05-29",
            "note": f"Arrangement available based on stated hardship reason: {hardship_reason}",
        },
    }


@function_tool
async def apply_goodwill_credit(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    amount_usd: float,
    rationale: str,
) -> dict:
    """Apply a one-time goodwill credit when within billing authority."""
    if not _is_verified(ctx):
        return _verification_required()
    approved = amount_usd <= 20
    if approved:
        latest_bill = await _repository().latest_bill()
        return {
            "requested_account_id": account_id,
            "approved": True,
            "credit_amount_usd": amount_usd,
            "posted_to_bill_id": latest_bill["bill_id"],
            "rationale": rationale,
        }
    return {
        "requested_account_id": account_id,
        "approved": False,
        "next_step": "Requires supervisor approval because the requested credit exceeds billing authority.",
    }


@function_tool
async def check_service_outage(
    ctx: RunContextWrapper[CallCenterContext],
    zip_code: str,
    service_type: str,
) -> dict:
    """Check whether the caller is affected by a service outage."""
    outage_detected = service_type == "home_internet" and zip_code == "98109"
    return {
        "zip_code": zip_code,
        "service_type": service_type,
        "outage_detected": outage_detected,
        "eta": "Estimated restoration in 2 hours" if outage_detected else "No area outage detected",
    }


@function_tool
async def run_line_diagnostics(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    line_id: str,
) -> dict:
    """Run line or device diagnostics on the account."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "line_id": line_id,
        "network_signal": "stable",
        "provisioning": "healthy",
        "device_registration": "intermittent modem impairment detected",
        "recommendation": "Power-cycle the gateway. If symptoms continue, schedule a technician.",
    }


@function_tool
async def schedule_technician(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    appointment_window: str,
    issue_summary: str,
) -> dict:
    """Schedule a technician visit in a supported appointment window."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "scheduled": True,
        "work_order_id": create_case_id("WO"),
        "appointment_window": appointment_window,
        "issue_summary": issue_summary,
    }


@function_tool
async def reboot_device_workflow(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    device_id: str,
) -> dict:
    """Trigger a remote reboot workflow for a registered device."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "device_id": device_id,
        "status": "reboot_sent",
        "expected_recovery_time": "3 to 5 minutes",
    }


@function_tool
async def lookup_plan_options(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
) -> dict:
    """Return available Atenxion plan options for the account."""
    if not _is_verified(ctx):
        return _verification_required()
    plan_catalog = await _repository().plan_catalog()
    return {
        "requested_account_id": account_id,
        "plans": plan_catalog,
    }


@function_tool
async def compare_plans(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    target_plan_code: str,
) -> dict:
    """Compare the customer's current plan against a target plan."""
    if not _is_verified(ctx):
        return _verification_required()
    customer_profile = await _repository().customer_profile()
    plan_catalog = await _repository().plan_catalog()
    target = next(
        (plan for plan in plan_catalog if plan["code"] == target_plan_code),
        None,
    )
    return {
        "requested_account_id": account_id,
        "current_plan": customer_profile["current_plan"],
        "target_plan": target,
        "tradeoff_summary": (
            f"Switching to {target['name']} changes the monthly rate to ${target['monthly_price_usd']} and changes included perks."
            if target
            else "Target plan not found."
        ),
    }


@function_tool
async def generate_retention_offer(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    risk_reason: str,
) -> dict:
    """Generate a retention offer for a customer considering cancellation."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "risk_reason": risk_reason,
        "offer": {
            "monthly_discount_usd": 15,
            "duration_months": 3,
            "alternate_option": "Move to Atenxion Start to reduce the monthly bill immediately.",
        },
    }


@function_tool
async def submit_cancellation_request(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    effective_date: str,
    reason: str,
) -> dict:
    """Submit a cancellation request for the account."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "cancellation_request_id": create_case_id("CANCEL"),
        "effective_date": effective_date,
        "reason": reason,
        "status": "pending_final_confirmation",
    }


@function_tool
async def lookup_policy_document(
    ctx: RunContextWrapper[CallCenterContext],
    topic: str,
) -> dict:
    """Look up an Atenxion policy document by topic."""
    policy_docs = await _repository().policy_docs()
    matches = [
        doc for doc in policy_docs if topic.lower() in doc["topic"].lower()
    ]
    return {"matches": matches}


@function_tool
async def approve_exception(
    ctx: RunContextWrapper[CallCenterContext],
    account_id: str,
    exception_type: str,
    justification: str,
) -> dict:
    """Approve or deny a policy exception for the account."""
    if not _is_verified(ctx):
        return _verification_required()
    return {
        "requested_account_id": account_id,
        "exception_type": exception_type,
        "approved": "credit" in exception_type.lower(),
        "decision_note": f"Supervisor reviewed the exception request. Justification noted: {justification}",
    }


@function_tool
async def escalation_decision(
    ctx: RunContextWrapper[CallCenterContext],
    case_summary: str,
    customer_sentiment: str,
    requested_outcome: str,
) -> dict:
    """Return a supervisor decision for an escalated call."""
    return {
        "decision": (
            "Take ownership, apologize clearly, and provide one concrete next step before asking anything else."
            if "angry" in customer_sentiment.lower()
            else "Acknowledge the prior work, answer directly, and confirm the requested outcome."
        ),
        "case_summary": case_summary,
        "requested_outcome": requested_outcome,
    }
