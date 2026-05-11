import type { AgentOption } from "../types";

export const callcenteragentScenario: AgentOption[] = [
  {
    name: "callcenteragent",
    handoffDescription:
      "Alice, Atenxion customer triage agent, welcomes callers, verifies them, creates case context, and routes them to the right specialist.",
  },
  {
    name: "billingAgent",
    handoffDescription:
      "Austin, Atenxion billing specialist for charges, bill review, payment arrangements, and goodwill credits.",
  },
  {
    name: "technicalSupportAgent",
    handoffDescription:
      "Bob, Atenxion technical support specialist for outages, diagnostics, reboots, and technician visits.",
  },
  {
    name: "retentionAgent",
    handoffDescription:
      "Maya, Atenxion retention specialist for save offers, plan comparisons, downgrades, and cancellation handling.",
  },
  {
    name: "supervisorAgent",
    handoffDescription:
      "Sarah, Atenxion supervisor for policy review, escalated decisions, and exception approvals.",
  },
  {
    name: "humanEscalationAgent",
    handoffDescription:
      "Jordan, Atenxion live-escalation style specialist for upset callers or explicit human escalation requests.",
  },
];
