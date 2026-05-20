"""Builds the OpenAI Realtime SDK agent network with the same scenario tools and handoff topology as the text graph."""
from agents.realtime import RealtimeAgent

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
    create_customer_ticket_via_mcp,
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
    search_customer_tickets_via_mcp,
    search_atenxion_knowledge_base,
    search_gmail_customer_history,
    send_customer_followup_email_via_mcp,
    submit_cancellation_request,
    verify_caller,
)

SHARED_VOICE = "sage"


def build_callcenter_realtime_agents() -> dict[str, RealtimeAgent[CallCenterContext]]:
    """Construct the OpenAI RealtimeAgent map used by the native realtime runtime."""
    shared_tools = [
        lookup_customer_profile,
        verify_caller,
        lookup_active_services,
        create_case,
        add_case_note,
    ]
    mcp_workflow_tools = [
        search_gmail_customer_history,
        send_customer_followup_email_via_mcp,
        search_customer_tickets_via_mcp,
        create_customer_ticket_via_mcp,
    ]

    callcenter_agent = RealtimeAgent[CallCenterContext](
        name="callcenteragent",
        handoff_description=(
            "Atenxion triage agent that welcomes callers, verifies them, creates case context, "
            "and routes them to the right specialist."
        ),
        instructions=CALLCENTER_AGENT_PROMPT,
        tools=[*shared_tools],
        handoffs=[],
    )

    billing_agent = RealtimeAgent[CallCenterContext](
        name="billingAgent",
        handoff_description=(
            "Atenxion billing specialist for charges, bill review, payment arrangements, "
            "and goodwill credits."
        ),
        instructions=BILLING_AGENT_PROMPT,
        tools=[
            *shared_tools,
            get_latest_bill,
            explain_charge_breakdown,
            offer_payment_arrangement,
            apply_goodwill_credit,
        ],
        handoffs=[],
    )

    technical_support_agent = RealtimeAgent[CallCenterContext](
        name="technicalSupportAgent",
        handoff_description=(
            "Atenxion technical support specialist for outages, diagnostics, reboots, and "
            "technician visits."
        ),
        instructions=TECHNICAL_SUPPORT_AGENT_PROMPT,
        tools=[
            *shared_tools,
            check_service_outage,
            run_line_diagnostics,
            schedule_technician,
            reboot_device_workflow,
        ],
        handoffs=[],
    )

    retention_agent = RealtimeAgent[CallCenterContext](
        name="retentionAgent",
        handoff_description=(
            "Atenxion retention specialist for save offers, plan comparisons, downgrades, and "
            "cancellation handling."
        ),
        instructions=RETENTION_AGENT_PROMPT,
        tools=[
            *shared_tools,
            lookup_plan_options,
            compare_plans,
            generate_retention_offer,
            submit_cancellation_request,
        ],
        handoffs=[],
    )

    supervisor_agent = RealtimeAgent[CallCenterContext](
        name="supervisorAgent",
        handoff_description=(
            "Atenxion supervisor for policy review, escalated decisions, and exception approvals."
        ),
        instructions=SUPERVISOR_AGENT_PROMPT,
        tools=[
            *shared_tools,
            lookup_policy_document,
            search_atenxion_knowledge_base,
            approve_exception,
            escalation_decision,
            *mcp_workflow_tools,
        ],
        handoffs=[],
    )

    human_escalation_agent = RealtimeAgent[CallCenterContext](
        name="humanEscalationAgent",
        handoff_description=(
            "Atenxion live-escalation style specialist for upset callers or explicit human "
            "escalation requests."
        ),
        instructions=HUMAN_ESCALATION_AGENT_PROMPT,
        tools=[*shared_tools, *mcp_workflow_tools],
        handoffs=[],
    )

    callcenter_agent.handoffs.extend(
        [
            billing_agent,
            technical_support_agent,
            retention_agent,
            supervisor_agent,
            human_escalation_agent,
        ]
    )
    billing_agent.handoffs.extend(
        [
            callcenter_agent,
            technical_support_agent,
            retention_agent,
            supervisor_agent,
            human_escalation_agent,
        ]
    )
    technical_support_agent.handoffs.extend(
        [
            callcenter_agent,
            billing_agent,
            retention_agent,
            supervisor_agent,
            human_escalation_agent,
        ]
    )
    retention_agent.handoffs.extend(
        [
            callcenter_agent,
            billing_agent,
            technical_support_agent,
            supervisor_agent,
            human_escalation_agent,
        ]
    )
    supervisor_agent.handoffs.extend(
        [
            callcenter_agent,
            billing_agent,
            technical_support_agent,
            retention_agent,
            human_escalation_agent,
        ]
    )
    human_escalation_agent.handoffs.extend(
        [
            callcenter_agent,
            billing_agent,
            technical_support_agent,
            retention_agent,
            supervisor_agent,
        ]
    )

    return {
        callcenter_agent.name: callcenter_agent,
        billing_agent.name: billing_agent,
        technical_support_agent.name: technical_support_agent,
        retention_agent.name: retention_agent,
        supervisor_agent.name: supervisor_agent,
        human_escalation_agent.name: human_escalation_agent,
    }
