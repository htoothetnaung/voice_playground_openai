"""Builds the non-realtime OpenAI Agents SDK Agent network, assigns tools, and wires handoffs between call-center specialists."""
from agents import Agent

from app.agents.callcenter.context import CallCenterContext
from app.agents.callcenter.prompts import (
    BILLING_AGENT_PROMPT,
    CALLCENTER_AGENT_PROMPT,
    HUMAN_ESCALATION_AGENT_PROMPT,
    RETENTION_AGENT_PROMPT,
    SUPERVISOR_AGENT_PROMPT,
    TECHNICAL_SUPPORT_AGENT_PROMPT,
)
from app.agents.callcenter.tools import (
    add_case_note,
    apply_goodwill_credit,
    approve_exception,
    check_service_outage,
    compare_plans,
    create_case,
    escalation_decision,
    explain_charge_breakdown,
    generate_retention_offer,
    get_latest_bill,
    lookup_active_services,
    lookup_customer_profile,
    lookup_plan_options,
    lookup_policy_document,
    offer_payment_arrangement,
    reboot_device_workflow,
    run_line_diagnostics,
    schedule_technician,
    submit_cancellation_request,
    verify_caller,
)


def _agent_kwargs(model: str | None) -> dict[str, str]:
    """Build optional Agent constructor kwargs so model overrides are only passed when configured."""
    return {"model": model} if model else {}


def build_callcenter_agent_map(model: str | None = None) -> dict[str, Agent[CallCenterContext]]:
    """Construct the full OpenAI Agents SDK text agent map with tools and bidirectional handoffs."""
    shared_tools = [
        lookup_customer_profile,
        verify_caller,
        lookup_active_services,
        create_case,
        add_case_note,
    ]

    billing_agent: Agent[CallCenterContext] = Agent(
        name="billingAgent",
        instructions=BILLING_AGENT_PROMPT,
        handoff_description="Atenxion billing specialist for charges, bill review, payment arrangements, and goodwill credits.",
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            get_latest_bill,
            explain_charge_breakdown,
            offer_payment_arrangement,
            apply_goodwill_credit,
        ],
    )

    technical_support_agent: Agent[CallCenterContext] = Agent(
        name="technicalSupportAgent",
        instructions=TECHNICAL_SUPPORT_AGENT_PROMPT,
        handoff_description="Atenxion technical support specialist for outages, diagnostics, reboots, and technician visits.",
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            check_service_outage,
            run_line_diagnostics,
            schedule_technician,
            reboot_device_workflow,
        ],
    )

    retention_agent: Agent[CallCenterContext] = Agent(
        name="retentionAgent",
        instructions=RETENTION_AGENT_PROMPT,
        handoff_description="Atenxion retention specialist for save offers, plan comparisons, downgrades, and cancellation handling.",
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            lookup_plan_options,
            compare_plans,
            generate_retention_offer,
            submit_cancellation_request,
        ],
    )

    supervisor_agent: Agent[CallCenterContext] = Agent(
        name="supervisorAgent",
        instructions=SUPERVISOR_AGENT_PROMPT,
        handoff_description="Atenxion supervisor for policy review, escalated decisions, and exception approvals.",
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            lookup_policy_document,
            approve_exception,
            escalation_decision,
        ],
    )

    human_escalation_agent: Agent[CallCenterContext] = Agent(
        name="humanEscalationAgent",
        instructions=HUMAN_ESCALATION_AGENT_PROMPT,
        handoff_description="Atenxion live-escalation style specialist for upset callers or explicit human escalation requests.",
        **_agent_kwargs(model),
        tools=[*shared_tools],
    )

    callcenter_agent: Agent[CallCenterContext] = Agent(
        name="callcenteragent",
        instructions=CALLCENTER_AGENT_PROMPT,
        handoff_description="Atenxion triage agent that welcomes callers, verifies them, creates case context, and routes them to the right specialist.",
        **_agent_kwargs(model),
        tools=[*shared_tools],
        handoffs=[
            billing_agent,
            technical_support_agent,
            retention_agent,
            supervisor_agent,
            human_escalation_agent,
        ],
    )

    billing_agent.handoffs = [
        callcenter_agent,
        technical_support_agent,
        retention_agent,
        supervisor_agent,
        human_escalation_agent,
    ]
    technical_support_agent.handoffs = [
        callcenter_agent,
        billing_agent,
        retention_agent,
        supervisor_agent,
        human_escalation_agent,
    ]
    retention_agent.handoffs = [
        callcenter_agent,
        billing_agent,
        technical_support_agent,
        supervisor_agent,
        human_escalation_agent,
    ]
    supervisor_agent.handoffs = [
        callcenter_agent,
        billing_agent,
        technical_support_agent,
        retention_agent,
        human_escalation_agent,
    ]
    human_escalation_agent.handoffs = [
        callcenter_agent,
        billing_agent,
        technical_support_agent,
        retention_agent,
        supervisor_agent,
    ]
    return {
        callcenter_agent.name: callcenter_agent,
        billing_agent.name: billing_agent,
        technical_support_agent.name: technical_support_agent,
        retention_agent.name: retention_agent,
        supervisor_agent.name: supervisor_agent,
        human_escalation_agent.name: human_escalation_agent,
    }


def build_callcenter_agent_graph(model: str | None = None) -> Agent[CallCenterContext]:
    """Return the triage agent that acts as the entry point for text SDK runs."""
    return build_callcenter_agent_map(model=model)["callcenteragent"]
