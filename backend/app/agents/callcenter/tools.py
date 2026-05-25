"""Implements account lookup, verification, billing, technical support, retention, supervisor, and case-management tool behavior over mock data."""
import re
from time import monotonic
from typing import Any

from agents import RunContextWrapper, function_tool
from openai import AsyncOpenAI

from app.agents.callcenter.bank_tool import (
    ATENXION_BANK_TOOL_NAME,
    fetch_atenxion_bank_transactions,
)
from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.data_repository import CallCenterDataRepository
from app.agents.callcenter.mcp_integrations import (
    MCP_DOC_SUMMARY,
    gmail_connector_tool,
    remote_email_tool,
    remote_ticketing_tool,
    run_mcp_response,
    validate_email,
)
from app.core.config import Settings, get_settings

def create_case_id(prefix: str) -> str:
    """Create deterministic demo case or work-order identifiers tied to the mock Atenxion account."""
    return f"{prefix}-ATX-204871-01"


def _repository() -> CallCenterDataRepository:
    """Create the data repository used by async tool functions."""
    return CallCenterDataRepository()


def _settings() -> Settings:
    return get_settings()


def _openai_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _verification_required() -> dict:
    """Return the standard tool response that prevents account-specific data before caller verification."""
    return {
        "authorized": False,
        "security_status": "verification_required",
        "next_step": "Do not provide account-specific details yet. Ask the caller for the phone number on the account first.",
    }


def _is_verified(ctx: RunContextWrapper[CallCenterContext]) -> bool:
    """Read the SDK run context to determine whether account-specific tools may proceed."""
    return bool(ctx.context.verified)


def _digits_only(value: str) -> str:
    """Normalize identity fields that may be spoken or typed with separators."""
    return re.sub(r"\D", "", value or "")


def _clamp_search_result_count(max_num_results: int) -> int:
    return max(1, min(int(max_num_results or 5), 50))


def _build_vector_store_search_filters(
    topic: str | None = None,
    service_type: str | None = None,
) -> dict[str, Any] | None:
    filters = []
    if topic:
        filters.append({"type": "eq", "key": "topic", "value": topic})
    if service_type:
        filters.append({"type": "eq", "key": "service_type", "value": service_type})
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"type": "and", "filters": filters}


def _build_vector_store_search_payload(
    query: str,
    max_num_results: int = 5,
    topic: str | None = None,
    service_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "max_num_results": _clamp_search_result_count(max_num_results),
        "rewrite_query": True,
    }
    filters = _build_vector_store_search_filters(topic=topic, service_type=service_type)
    if filters:
        payload["filters"] = filters
    return payload


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _normalize_search_results(response: Any, elapsed_ms: float) -> dict[str, Any]:
    payload = _object_to_dict(response)
    return _normalize_search_result_items(
        payload.get("data", []) or [],
        elapsed_ms,
        search_query=payload.get("search_query"),
        has_more=bool(payload.get("has_more", False)),
    )


def _normalize_search_result_items(
    items: list[Any],
    elapsed_ms: float,
    *,
    search_query: Any = None,
    has_more: bool = False,
) -> dict[str, Any]:
    results = []
    for item in items:
        mapped = _object_to_dict(item)
        snippets = []
        for content in mapped.get("content", []) or []:
            content_item = _object_to_dict(content)
            text = str(content_item.get("text", "")).strip()
            if text:
                snippets.append(text[:600])
        results.append(
            {
                "file_id": mapped.get("file_id"),
                "filename": mapped.get("filename"),
                "score": mapped.get("score"),
                "attributes": mapped.get("attributes") or {},
                "snippets": snippets,
            }
        )
    return {
        "available": True,
        "result_count": len(results),
        "results": results,
        "search_query": search_query,
        "has_more": has_more,
        "latency_ms": round(elapsed_ms, 3),
    }


async def _search_atenxion_vector_store(
    client: AsyncOpenAI,
    vector_store_id: str,
    *,
    query: str,
    max_num_results: int = 5,
    topic: str | None = None,
    service_type: str | None = None,
) -> dict[str, Any]:
    start = monotonic()
    payload = _build_vector_store_search_payload(
        query=query,
        max_num_results=max_num_results,
        topic=topic,
        service_type=service_type,
    )
    paginator = client.vector_stores.search(vector_store_id, **payload)
    items = []
    async for item in paginator:
        items.append(item)
    return _normalize_search_result_items(items, (monotonic() - start) * 1000)


async def _search_atenxion_knowledge_base_impl(
    settings: Settings,
    *,
    query: str,
    max_num_results: int = 5,
    topic: str | None = None,
    service_type: str | None = None,
    client: AsyncOpenAI | None = None,
) -> dict[str, Any]:
    vector_store_id = settings.callcenter_rag_vector_store_id
    if not vector_store_id:
        return {
            "available": False,
            "reason": "CALLCENTER_RAG_VECTOR_STORE_ID is not configured.",
            "results": [],
            "result_count": 0,
        }
    try:
        return await _search_atenxion_vector_store(
            client or _openai_client(settings),
            vector_store_id,
            query=query,
            max_num_results=max_num_results,
            topic=topic,
            service_type=service_type,
        )
    except Exception as exc:
        return {
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "results": [],
            "result_count": 0,
        }


@function_tool
async def lookup_customer_profile(
    ctx: RunContextWrapper[CallCenterContext],
    phone_number: str,
) -> dict:
    """Look up the Atenxion customer profile by phone number."""
    customer_profile = await _repository().customer_profile()
    matched = _digits_only(phone_number) == _digits_only(
        customer_profile["phone_number"]
    )
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
) -> dict:
    """Verify the caller using the account phone number."""
    customer_profile = await _repository().customer_profile()
    verified = _digits_only(phone_number) == _digits_only(customer_profile["phone_number"])
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
            "Do not transfer or escalate. Tell the caller the phone number does not match Atenxion's records. Ask them to check their account details "
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


@function_tool(name_override=ATENXION_BANK_TOOL_NAME)
async def atenxion_bank_tool(
    ctx: RunContextWrapper[CallCenterContext],
    user_id: str,
) -> dict:
    """
    Retrieve completed Atenxion Bank transaction details by user ID.

    Important tool-calling rule:
    - Before calling this tool, you must know the bank user ID.
    - If the caller asks about bank transactions but has not provided a user ID, ask a follow-up question first.
    - Do not guess missing required fields.
    """
    if not _is_verified(ctx):
        return _verification_required()
    return await fetch_atenxion_bank_transactions(_settings(), user_id=user_id)


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
async def search_atenxion_knowledge_base(
    ctx: RunContextWrapper[CallCenterContext],
    query: str,
    max_num_results: int = 5,
    topic: str | None = None,
    service_type: str | None = None,
) -> dict:
    """Search Atenxion's OpenAI vector store for policy, troubleshooting, billing, and retention knowledge."""
    return await _search_atenxion_knowledge_base_impl(
        _settings(),
        query=query,
        max_num_results=max_num_results,
        topic=topic,
        service_type=service_type,
    )


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


@function_tool
async def search_gmail_customer_history(
    ctx: RunContextWrapper[CallCenterContext],
    customer_email: str,
    query: str,
) -> dict:
    """Search recent customer email history through the official Gmail MCP connector."""
    if not _is_verified(ctx):
        return _verification_required()
    settings = _settings()
    tool = gmail_connector_tool(settings)
    if tool is None:
        return {
            "available": False,
            "reason": "MCP_GMAIL_OAUTH_TOKEN is not configured.",
            "doc_note": MCP_DOC_SUMMARY,
        }
    if not validate_email(customer_email):
        return {"available": False, "reason": "customer_email must be a valid email address."}
    result = await run_mcp_response(
        _openai_client(settings),
        settings,
        tool_name="gmail_customer_history",
        tool=tool,
        input_text=(
            "Use the Gmail connector to find customer-support related messages for "
            f"{customer_email}. Query: {query}. Return only a compact summary of relevant threads."
        ),
    )
    return {**result, "customer_email": customer_email}


@function_tool
async def send_customer_followup_email_via_mcp(
    ctx: RunContextWrapper[CallCenterContext],
    recipient_email: str,
    subject: str,
    body: str,
    case_id: str | None = None,
) -> dict:
    """Send or draft a customer follow-up email through a configured trusted remote MCP email server."""
    if not _is_verified(ctx):
        return _verification_required()
    settings = _settings()
    tool = remote_email_tool(settings)
    if tool is None:
        return {
            "available": False,
            "reason": "MCP_EMAIL_SERVER_URL is not configured.",
            "doc_note": MCP_DOC_SUMMARY,
            "recommended_path": (
                "The official Gmail connector is useful for read/search. For sending email, configure a "
                "trusted remote MCP server that exposes send_email or create_draft and set MCP_EMAIL_ALLOWED_TOOLS."
            ),
        }
    if not validate_email(recipient_email):
        return {"available": False, "reason": "recipient_email must be a valid email address."}
    result = await run_mcp_response(
        _openai_client(settings),
        settings,
        tool_name="customer_followup_email",
        tool=tool,
        input_text=(
            "Use the configured customer email MCP server to send or draft this verified support follow-up. "
            f"Recipient: {recipient_email}\nSubject: {subject}\nCase ID: {case_id or ctx.context.case_id or 'not provided'}\n"
            f"Body:\n{body}"
        ),
    )
    return {
        **result,
        "recipient_email": recipient_email,
        "case_id": case_id or ctx.context.case_id,
        "sent": bool(result["mcp_call_count"] and not result["approval_required"] and not result["errors"]),
    }


@function_tool
async def search_customer_tickets_via_mcp(
    ctx: RunContextWrapper[CallCenterContext],
    customer_identifier: str,
    query: str,
) -> dict:
    """Search customer-service tickets through a configured Zendesk or Zoho Desk style remote MCP server."""
    if not _is_verified(ctx):
        return _verification_required()
    settings = _settings()
    tool = remote_ticketing_tool(settings)
    if tool is None:
        return {
            "available": False,
            "reason": "MCP_TICKETING_SERVER_URL is not configured.",
            "recommended_path": "Configure an official or trusted Zendesk/Zoho Desk remote MCP server when selected.",
        }
    result = await run_mcp_response(
        _openai_client(settings),
        settings,
        tool_name="customer_ticket_search",
        tool=tool,
        input_text=(
            "Use the configured customer ticketing MCP server to search existing complaints and tickets. "
            f"Customer identifier: {customer_identifier}. Query: {query}. Return compact ticket IDs, statuses, and next actions."
        ),
    )
    return {**result, "customer_identifier": customer_identifier}


@function_tool
async def create_customer_ticket_via_mcp(
    ctx: RunContextWrapper[CallCenterContext],
    customer_identifier: str,
    title: str,
    complaint_summary: str,
    priority: str,
) -> dict:
    """Create a customer complaint ticket through a configured Zendesk or Zoho Desk style remote MCP server."""
    if not _is_verified(ctx):
        return _verification_required()
    settings = _settings()
    tool = remote_ticketing_tool(settings)
    if tool is None:
        return {
            "available": False,
            "reason": "MCP_TICKETING_SERVER_URL is not configured.",
            "recommended_path": "Configure an official or trusted Zendesk/Zoho Desk remote MCP server when selected.",
        }
    result = await run_mcp_response(
        _openai_client(settings),
        settings,
        tool_name="customer_ticket_create",
        tool=tool,
        input_text=(
            "Use the configured customer ticketing MCP server to create a customer complaint ticket. "
            f"Customer identifier: {customer_identifier}\nTitle: {title}\nPriority: {priority}\n"
            f"Complaint summary: {complaint_summary}"
        ),
    )
    return {
        **result,
        "customer_identifier": customer_identifier,
        "ticket_created": bool(result["mcp_call_count"] and not result["approval_required"] and not result["errors"]),
    }
