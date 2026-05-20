"""Builds the Google ADK LlmAgent network for the Atenxion call-center specialists."""
from google.adk.agents import LlmAgent

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
    search_atenxion_knowledge_base,
    submit_cancellation_request,
    verify_caller,
)


def _transfer_instruction(agent_names: list[str]) -> str:
    choices = ", ".join(agent_names)
    return (
        "\n\nGoogle ADK routing: when a caller's issue belongs with another specialist, "
        "use ADK's transfer_to_agent action to route to exactly one of these agents: "
        f"{choices}. Transfer only after required identity verification for account-specific work."
    )


def _agent_kwargs(model: str) -> dict[str, str]:
    return {"model": model}


def build_callcenter_agent_map(model: str = "gemini-2.5-flash") -> dict[str, LlmAgent]:
    """Construct the ADK agent map with the same names, prompts, tools, and specialist roles."""
    shared_tools = [
        lookup_customer_profile,
        verify_caller,
        lookup_active_services,
        create_case,
        add_case_note,
    ]
    specialist_names = [
        "billingAgent",
        "technicalSupportAgent",
        "retentionAgent",
        "supervisorAgent",
        "humanEscalationAgent",
    ]

    billing_agent = LlmAgent(
        name="billingAgent",
        description="Atenxion billing specialist for charges, bill review, payment arrangements, and goodwill credits.",
        instruction=BILLING_AGENT_PROMPT + _transfer_instruction(["callcenteragent", *specialist_names]),
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            get_latest_bill,
            explain_charge_breakdown,
            offer_payment_arrangement,
            apply_goodwill_credit,
        ],
    )

    technical_support_agent = LlmAgent(
        name="technicalSupportAgent",
        description="Atenxion technical support specialist for outages, diagnostics, reboots, and technician visits.",
        instruction=TECHNICAL_SUPPORT_AGENT_PROMPT + _transfer_instruction(["callcenteragent", *specialist_names]),
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            check_service_outage,
            run_line_diagnostics,
            schedule_technician,
            reboot_device_workflow,
        ],
    )

    retention_agent = LlmAgent(
        name="retentionAgent",
        description="Atenxion retention specialist for save offers, plan comparisons, downgrades, and cancellation handling.",
        instruction=RETENTION_AGENT_PROMPT + _transfer_instruction(["callcenteragent", *specialist_names]),
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            lookup_plan_options,
            compare_plans,
            generate_retention_offer,
            submit_cancellation_request,
        ],
    )

    supervisor_agent = LlmAgent(
        name="supervisorAgent",
        description="Atenxion supervisor for policy review, escalated decisions, and exception approvals.",
        instruction=SUPERVISOR_AGENT_PROMPT + _transfer_instruction(["callcenteragent", *specialist_names]),
        **_agent_kwargs(model),
        tools=[
            *shared_tools,
            lookup_policy_document,
            search_atenxion_knowledge_base,
            approve_exception,
            escalation_decision,
        ],
    )

    human_escalation_agent = LlmAgent(
        name="humanEscalationAgent",
        description="Atenxion live-escalation style specialist for upset callers or explicit human escalation requests.",
        instruction=HUMAN_ESCALATION_AGENT_PROMPT + _transfer_instruction(["callcenteragent", *specialist_names]),
        **_agent_kwargs(model),
        tools=[*shared_tools],
    )

    callcenter_agent = LlmAgent(
        name="callcenteragent",
        description="Atenxion triage agent that welcomes callers, verifies them, creates case context, and routes them to the right specialist.",
        instruction=CALLCENTER_AGENT_PROMPT + _transfer_instruction(specialist_names),
        **_agent_kwargs(model),
        tools=[*shared_tools],
        sub_agents=[
            billing_agent,
            technical_support_agent,
            retention_agent,
            supervisor_agent,
            human_escalation_agent,
        ],
    )

    return {
        callcenter_agent.name: callcenter_agent,
        billing_agent.name: billing_agent,
        technical_support_agent.name: technical_support_agent,
        retention_agent.name: retention_agent,
        supervisor_agent.name: supervisor_agent,
        human_escalation_agent.name: human_escalation_agent,
    }


def build_callcenter_agent_graph(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Return the ADK triage agent that acts as the entry point for text runs."""
    return build_callcenter_agent_map(model=model)["callcenteragent"]
