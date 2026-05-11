import { tool } from "@openai/agents/realtime";

import {
  atenxionActiveServices,
  atenxionCustomerProfile,
  atenxionLatestBill,
  atenxionPlanCatalog,
  atenxionPolicyDocs,
} from "./mockData";

function createCaseId(prefix: string) {
  return `${prefix}-${atenxionCustomerProfile.account_id}-01`;
}

export const sharedCallCenterTools = [
  tool({
    name: "lookupCustomerProfile",
    description: "Look up the Atenxion customer profile by phone number.",
    parameters: {
      type: "object",
      properties: {
        phone_number: {
          type: "string",
          description: "Customer phone number formatted like '(206) 555-0147'.",
        },
      },
      required: ["phone_number"],
      additionalProperties: false,
    },
    execute: async (input: any) => {
      const { phone_number } = input;
      const matched = phone_number === atenxionCustomerProfile.phone_number;
      return matched
        ? {
            found: true,
            profile: {
              account_id: atenxionCustomerProfile.account_id,
              full_name: atenxionCustomerProfile.full_name,
              phone_number: atenxionCustomerProfile.phone_number,
              service_address: atenxionCustomerProfile.service_address,
              current_plan: atenxionCustomerProfile.current_plan,
              sentiment: atenxionCustomerProfile.sentiment,
            },
          }
        : {
            found: false,
            next_step: "Ask the caller to confirm the callback number on the account.",
          };
    },
  }),
  tool({
    name: "verifyCaller",
    description: "Verify the caller using phone number, date of birth, and 4-digit PIN.",
    parameters: {
      type: "object",
      properties: {
        phone_number: { type: "string" },
        date_of_birth: { type: "string", description: "Format 'YYYY-MM-DD'." },
        pin_last4: { type: "string", description: "4-digit PIN." },
      },
      required: ["phone_number", "date_of_birth", "pin_last4"],
      additionalProperties: false,
    },
    execute: async (input: any) => {
      const { phone_number, date_of_birth, pin_last4 } = input;
      const verified =
        phone_number === atenxionCustomerProfile.phone_number &&
        date_of_birth === atenxionCustomerProfile.date_of_birth &&
        pin_last4 === atenxionCustomerProfile.pin_last4;
      return verified
        ? {
            verified: true,
            account_id: atenxionCustomerProfile.account_id,
            security_status: "passed",
          }
        : {
            verified: false,
            security_status: "failed",
            next_step: "Ask the caller to re-confirm the date of birth and 4-digit PIN.",
          };
    },
  }),
  tool({
    name: "lookupActiveServices",
    description: "Return the active Atenxion services on an account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
      },
      required: ["account_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      services: atenxionActiveServices.services,
    }),
  }),
  tool({
    name: "createCase",
    description: "Create a support case with a team owner and priority.",
    parameters: {
      type: "object",
      properties: {
        reason: { type: "string" },
        priority: { type: "string", enum: ["low", "medium", "high"] },
        owning_team: {
          type: "string",
          enum: ["frontdesk", "billing", "technical_support", "retention", "supervisor"],
        },
      },
      required: ["reason", "priority", "owning_team"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      case_id: createCaseId("CASE"),
      status: "open",
      reason: input.reason,
      priority: input.priority,
      owning_team: input.owning_team,
    }),
  }),
  tool({
    name: "addCaseNote",
    description: "Attach an internal case note to an existing support case.",
    parameters: {
      type: "object",
      properties: {
        case_id: { type: "string" },
        note: { type: "string" },
        visibility: { type: "string", enum: ["internal", "customer_safe"] },
      },
      required: ["case_id", "note", "visibility"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      case_id: input.case_id,
      saved: true,
      note_preview: String(input.note).slice(0, 140),
      visibility: input.visibility,
    }),
  }),
];

export const billingTools = [
  tool({
    name: "getLatestBill",
    description: "Fetch the latest Atenxion bill for an account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
      },
      required: ["account_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      ...atenxionLatestBill,
    }),
  }),
  tool({
    name: "explainChargeBreakdown",
    description: "Explain the bill line items in plain language.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        bill_id: { type: "string" },
      },
      required: ["account_id", "bill_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      bill_id: input.bill_id,
      explanation: [
        "The bill increased mainly because of international calls and two roaming day passes.",
        "The base plan stayed the same month over month.",
        "Device protection and taxes were consistent with the prior bill.",
      ],
      driver_summary: "Usage-based travel charges caused most of the increase.",
    }),
  }),
  tool({
    name: "offerPaymentArrangement",
    description: "Offer an eligible short-term payment arrangement.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        hardship_reason: { type: "string" },
      },
      required: ["account_id", "hardship_reason"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      eligible: true,
      offer: {
        deferred_amount_usd: 60,
        deferred_until: "2026-05-29",
        note: `Arrangement available based on stated hardship reason: ${input.hardship_reason}`,
      },
    }),
  }),
  tool({
    name: "applyGoodwillCredit",
    description: "Apply a one-time goodwill credit when within billing authority.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        amount_usd: { type: "number" },
        rationale: { type: "string" },
      },
      required: ["account_id", "amount_usd", "rationale"],
      additionalProperties: false,
    },
    execute: async (input: any) => {
      const approved = Number(input.amount_usd) <= 20;
      return approved
        ? {
            requested_account_id: input.account_id,
            approved: true,
            credit_amount_usd: input.amount_usd,
            posted_to_bill_id: atenxionLatestBill.bill_id,
            rationale: input.rationale,
          }
        : {
            requested_account_id: input.account_id,
            approved: false,
            next_step:
              "Requires supervisor approval because the requested credit exceeds billing authority.",
          };
    },
  }),
];

export const technicalSupportTools = [
  tool({
    name: "checkServiceOutage",
    description: "Check whether the caller is affected by a service outage.",
    parameters: {
      type: "object",
      properties: {
        zip_code: { type: "string" },
        service_type: {
          type: "string",
          enum: ["mobile", "home_internet", "tablet_data"],
        },
      },
      required: ["zip_code", "service_type"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      zip_code: input.zip_code,
      service_type: input.service_type,
      outage_detected:
        input.service_type === "home_internet" && input.zip_code === "98109",
      eta:
        input.service_type === "home_internet" && input.zip_code === "98109"
          ? "Estimated restoration in 2 hours"
          : "No area outage detected",
    }),
  }),
  tool({
    name: "runLineDiagnostics",
    description: "Run line or device diagnostics on the account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        line_id: { type: "string" },
      },
      required: ["account_id", "line_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      line_id: input.line_id,
      network_signal: "stable",
      provisioning: "healthy",
      device_registration: "intermittent modem impairment detected",
      recommendation:
        "Power-cycle the gateway. If symptoms continue, schedule a technician.",
    }),
  }),
  tool({
    name: "scheduleTechnician",
    description: "Schedule a technician visit in a supported appointment window.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        appointment_window: { type: "string" },
        issue_summary: { type: "string" },
      },
      required: ["account_id", "appointment_window", "issue_summary"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      scheduled: true,
      work_order_id: createCaseId("WO"),
      appointment_window: input.appointment_window,
      issue_summary: input.issue_summary,
    }),
  }),
  tool({
    name: "rebootDeviceWorkflow",
    description: "Trigger a remote reboot workflow for a registered device.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        device_id: { type: "string" },
      },
      required: ["account_id", "device_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      device_id: input.device_id,
      status: "reboot_sent",
      expected_recovery_time: "3 to 5 minutes",
    }),
  }),
];

export const retentionTools = [
  tool({
    name: "lookupPlanOptions",
    description: "Return available Atenxion plan options for the account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
      },
      required: ["account_id"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      plans: atenxionPlanCatalog,
    }),
  }),
  tool({
    name: "comparePlans",
    description: "Compare the customer’s current plan against a target plan.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        target_plan_code: { type: "string" },
      },
      required: ["account_id", "target_plan_code"],
      additionalProperties: false,
    },
    execute: async (input: any) => {
      const target = atenxionPlanCatalog.find(
        (plan) => plan.code === input.target_plan_code
      );
      return {
        requested_account_id: input.account_id,
        current_plan: atenxionCustomerProfile.current_plan,
        target_plan: target ?? null,
        tradeoff_summary: target
          ? `Switching to ${target.name} changes the monthly rate to $${target.monthly_price_usd} and changes included perks.`
          : "Target plan not found.",
      };
    },
  }),
  tool({
    name: "generateRetentionOffer",
    description: "Generate a retention offer for a customer considering cancellation.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        risk_reason: { type: "string" },
      },
      required: ["account_id", "risk_reason"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      risk_reason: input.risk_reason,
      offer: {
        monthly_discount_usd: 15,
        duration_months: 3,
        alternate_option:
          "Move to Atenxion Start to reduce the monthly bill immediately.",
      },
    }),
  }),
  tool({
    name: "submitCancellationRequest",
    description: "Submit a cancellation request for the account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        effective_date: { type: "string" },
        reason: { type: "string" },
      },
      required: ["account_id", "effective_date", "reason"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      cancellation_request_id: createCaseId("CANCEL"),
      effective_date: input.effective_date,
      reason: input.reason,
      status: "pending_final_confirmation",
    }),
  }),
];

export const supervisorTools = [
  tool({
    name: "lookupPolicyDocument",
    description: "Look up an Atenxion policy document by topic.",
    parameters: {
      type: "object",
      properties: {
        topic: { type: "string" },
      },
      required: ["topic"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      matches: atenxionPolicyDocs.filter((doc) =>
        doc.topic.toLowerCase().includes(String(input.topic).toLowerCase())
      ),
    }),
  }),
  tool({
    name: "approveException",
    description: "Approve or deny a policy exception for the account.",
    parameters: {
      type: "object",
      properties: {
        account_id: { type: "string" },
        exception_type: { type: "string" },
        justification: { type: "string" },
      },
      required: ["account_id", "exception_type", "justification"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      requested_account_id: input.account_id,
      exception_type: input.exception_type,
      approved: String(input.exception_type).toLowerCase().includes("credit"),
      decision_note: `Supervisor reviewed the exception request. Justification noted: ${input.justification}`,
    }),
  }),
  tool({
    name: "escalationDecision",
    description: "Return a supervisor decision for an escalated call.",
    parameters: {
      type: "object",
      properties: {
        case_summary: { type: "string" },
        customer_sentiment: { type: "string" },
        requested_outcome: { type: "string" },
      },
      required: ["case_summary", "customer_sentiment", "requested_outcome"],
      additionalProperties: false,
    },
    execute: async (input: any) => ({
      decision: String(input.customer_sentiment).includes("angry")
        ? "Take ownership, apologize clearly, and provide one concrete next step before asking anything else."
        : "Acknowledge the prior work, answer directly, and confirm the requested outcome.",
      case_summary: input.case_summary,
      requested_outcome: input.requested_outcome,
    }),
  }),
];
