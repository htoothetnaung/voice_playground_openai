"""Stores in-memory customer, billing, service, plan, and policy records used by tool functions for the demo scenario."""
ATENXION_CUSTOMER_PROFILE = {
    "account_id": "ATX-204871",
    "full_name": "Htoo Thet",
    "phone_number": "09661200650",
    "sentiment": "frustrated_but_cooperative",
    "tenure_years": 4,
    "autopay": True,
    "preferred_contact": "sms",
    "service_address": {
        "street": "1428 Aurora Avenue N",
        "city": "Seattle",
        "state": "WA",
        "postal_code": "98109",
    },
    "billing_address": {
        "street": "1428 Aurora Avenue N",
        "city": "Seattle",
        "state": "WA",
        "postal_code": "98109",
    },
    "current_plan": {
        "code": "ATX-UNLIMITED-PLUS",
        "name": "Unlimited Plus",
        "monthly_price_usd": 89,
    },
}

ATENXION_ACTIVE_SERVICES = {
    "services": [
        {
            "service_id": "SRV-MOB-01",
            "type": "5g_mobile",
            "status": "active",
            "line_id": "LINE-01",
            "plan_code": "ATX-UNLIMITED-PLUS",
        },
        {
            "service_id": "SRV-TAB-01",
            "type": "tablet_data",
            "status": "active",
            "line_id": "LINE-02",
            "plan_code": "ATX-TAB-10GB",
        },
        {
            "service_id": "SRV-HOME-01",
            "type": "home_internet",
            "status": "active",
            "speed_tier": "1 Gig",
            "modem_id": "ATX-GW-7781",
        },
    ]
}

ATENXION_LATEST_BILL = {
    "bill_id": "BILL-2026-04",
    "billing_period": "2026-04-01 to 2026-04-30",
    "due_date": "2026-05-15",
    "status": "due",
    "total_usd": 146.32,
    "prior_month_usd": 97.84,
    "summary": {
        "base_plan_usd": 89,
        "international_calls_usd": 22.14,
        "roaming_day_passes_usd": 18,
        "device_protection_usd": 12.99,
        "taxes_and_fees_usd": 4.19,
    },
}

ATENXION_PLAN_CATALOG = [
    {
        "code": "ATX-START",
        "name": "Atenxion Start",
        "monthly_price_usd": 55,
        "highlights": ["Unlimited talk and text", "30GB premium data", "No hotspot"],
    },
    {
        "code": "ATX-UNLIMITED-PLUS",
        "name": "Unlimited Plus",
        "monthly_price_usd": 89,
        "highlights": ["Unlimited premium data", "20GB hotspot", "International roaming perks"],
    },
    {
        "code": "ATX-FAMILY-FLEX",
        "name": "Family Flex",
        "monthly_price_usd": 135,
        "highlights": ["Up to 4 lines", "Shared hotspot pool", "Streaming bundle credit"],
    },
]

ATENXION_POLICY_DOCS = [
    {
        "id": "POL-001",
        "topic": "goodwill credit",
        "name": "Goodwill Credit Policy",
        "content": "Frontline billing agents may issue up to a $20 one-time credit per rolling 12-month period when charges are valid but goodwill is appropriate. Larger credits require supervisor approval.",
    },
    {
        "id": "POL-002",
        "topic": "payment arrangement",
        "name": "Payment Flex Policy",
        "content": "Eligible postpaid accounts in good standing may defer up to 50% of a past-due or current balance for 14 days. Accounts with repeated broken promises require supervisor review.",
    },
    {
        "id": "POL-003",
        "topic": "outage",
        "name": "Residential Outage Handling",
        "content": "If there is a verified area outage, agents should avoid repeated troubleshooting, set expectations, and offer a case note plus optional outage-follow-up text enrollment.",
    },
    {
        "id": "POL-004",
        "topic": "retention",
        "name": "Retention Save Guidelines",
        "content": "Retention agents may offer a three-month loyalty discount, a device protection waiver, or a downgrade path when a customer cites price pressure or cancellation intent.",
    },
    {
        "id": "POL-005",
        "topic": "technician",
        "name": "Technician Dispatch Rules",
        "content": "Technician visits may be scheduled in 2-hour windows from 8 AM to 6 PM local time when remote diagnostics show persistent impairment or customer equipment replacement is likely.",
    },
]


def _build_atenxion_rag_documents() -> list[dict]:
    """Build deterministic medium-size support documents for RAG and latency tests."""
    topics = [
        {
            "topic": "billing_dispute",
            "service_type": "mobile",
            "title": "Billing Dispute Review",
            "summary": "Validate disputed charges by checking bill period, line usage, plan features, credits, and customer-visible notices.",
            "guidance": "Agents should explain the largest variance first, separate recurring plan charges from usage-based charges, and create a case when the customer disputes a valid charge.",
        },
        {
            "topic": "roaming_charges",
            "service_type": "mobile",
            "title": "International Roaming Charge Handling",
            "summary": "Roaming day passes, international calls, and travel data can post after the usage date and may appear as delayed bill increases.",
            "guidance": "Check travel dates, line ID, country zone, and notification history before offering goodwill or supervisor review.",
        },
        {
            "topic": "taxes_and_fees",
            "service_type": "mobile",
            "title": "Taxes and Regulatory Fee Explanation",
            "summary": "Taxes and fees vary by billing address, service type, and local surcharge changes.",
            "guidance": "Avoid calling taxes discretionary. Explain that plan changes, device protection, and address changes can affect the total due.",
        },
        {
            "topic": "goodwill_credit",
            "service_type": "billing",
            "title": "Goodwill Credit Boundary",
            "summary": "Frontline credits are limited and should be used for customer experience recovery, not to erase valid recurring charges.",
            "guidance": "Credits above frontline authority require supervisor approval with a clear rationale and prior-credit check.",
        },
        {
            "topic": "payment_arrangement",
            "service_type": "billing",
            "title": "Payment Flex Arrangement",
            "summary": "Eligible postpaid customers may defer part of a current or past-due balance for a short window.",
            "guidance": "Confirm amount, due date, account standing, and previous broken arrangements before offering a payment extension.",
        },
        {
            "topic": "home_internet_outage",
            "service_type": "home_internet",
            "title": "Residential Outage Handling",
            "summary": "Area outages should be identified before repeated device troubleshooting or dispatch scheduling.",
            "guidance": "When an outage is verified, set expectations, offer follow-up enrollment, and avoid unnecessary modem replacement.",
        },
        {
            "topic": "line_diagnostics",
            "service_type": "home_internet",
            "title": "Line Diagnostic Interpretation",
            "summary": "Signal, provisioning, packet loss, and device registration results determine the next support step.",
            "guidance": "Persistent impairment after a gateway reboot can justify technician dispatch in the next available appointment window.",
        },
        {
            "topic": "device_reboot",
            "service_type": "home_internet",
            "title": "Gateway Reboot Workflow",
            "summary": "Remote reboot can resolve stale registration, firmware update stalls, and intermittent connectivity.",
            "guidance": "Warn the caller that service may drop for several minutes, then confirm recovery before scheduling a technician.",
        },
        {
            "topic": "retention_offer",
            "service_type": "retention",
            "title": "Retention Save Offer",
            "summary": "Save offers are intended for price pressure, competitor comparisons, and cancellation risk.",
            "guidance": "Compare the current plan with a lower-cost option before applying a temporary discount.",
        },
        {
            "topic": "cancellation",
            "service_type": "retention",
            "title": "Cancellation Request Handling",
            "summary": "Cancellation requests require confirmation of effective date, impacted services, remaining device balances, and final-bill expectations.",
            "guidance": "Do not pressure the customer. Confirm the request, summarize tradeoffs, and submit only after the customer confirms intent.",
        },
        {
            "topic": "plan_comparison",
            "service_type": "retention",
            "title": "Plan Comparison Guidance",
            "summary": "Plan changes can alter hotspot data, roaming perks, discounts, and streaming credits.",
            "guidance": "Mention the monthly price and the most important lost benefit before recommending a downgrade.",
        },
        {
            "topic": "supervisor_exception",
            "service_type": "supervisor",
            "title": "Supervisor Exception Review",
            "summary": "Supervisor decisions should balance policy, customer history, regulatory constraints, and recoverable customer experience failures.",
            "guidance": "Approve only when the exception has a documented rationale, a supported policy path, and a clear next action.",
        },
        {
            "topic": "escalation_playbook",
            "service_type": "supervisor",
            "title": "Escalation De-escalation Playbook",
            "summary": "Upset callers need ownership, a direct answer, and one concrete next step before more questions.",
            "guidance": "Acknowledge frustration, avoid blaming earlier agents, and use concise decision language after reviewing facts.",
        },
        {
            "topic": "technician_dispatch",
            "service_type": "field_service",
            "title": "Technician Dispatch Rules",
            "summary": "Dispatch is appropriate when remote diagnostics indicate persistent impairment or equipment replacement is likely.",
            "guidance": "Use a two-hour appointment window, capture issue symptoms, and avoid dispatch during known area outages.",
        },
        {
            "topic": "case_notes",
            "service_type": "case_management",
            "title": "Case Note Quality",
            "summary": "Case notes should capture the customer request, verified facts, tool outcomes, and promised next step.",
            "guidance": "Keep notes factual and concise. Do not include unsupported commitments or sensitive authentication details.",
        },
        {
            "topic": "fraud_security",
            "service_type": "account_security",
            "title": "Verification and Security Boundary",
            "summary": "Account-specific details require successful account phone-number verification.",
            "guidance": "Failed verification is not an escalation path. Ask the caller to check account details and call back.",
        },
    ]
    regions = [
        ("PNW", "Seattle", "WA", "98109"),
        ("PNW", "Portland", "OR", "97205"),
        ("Southwest", "Phoenix", "AZ", "85004"),
        ("Mountain", "Denver", "CO", "80202"),
        ("Midwest", "Chicago", "IL", "60601"),
        ("Northeast", "Boston", "MA", "02108"),
        ("Mid-Atlantic", "Baltimore", "MD", "21201"),
        ("Southeast", "Atlanta", "GA", "30303"),
        ("Texas", "Austin", "TX", "78701"),
        ("California", "San Diego", "CA", "92101"),
    ]
    severities = ["low", "medium", "high", "urgent"]
    audiences = ["frontline", "billing", "technical_support", "retention", "supervisor"]

    documents = []
    for index in range(1000):
        topic = topics[index % len(topics)]
        region, city, state, postal_code = regions[index % len(regions)]
        severity = severities[index % len(severities)]
        audience = audiences[index % len(audiences)]
        revision = 1 + (index % 12)
        scenario_id = f"ATX-RAG-{index + 1:04d}"
        documents.append(
            {
                "document_id": scenario_id,
                "title": f"{topic['title']} - {region} Scenario {index + 1:04d}",
                "topic": topic["topic"],
                "service_type": topic["service_type"],
                "region": region,
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "severity": severity,
                "audience": audience,
                "revision": revision,
                "content": (
                    f"{scenario_id}: {topic['summary']} This Atenxion knowledge record applies to "
                    f"{topic['service_type']} support in {city}, {state} ({postal_code}) for {audience} "
                    f"agents. Severity is {severity}. {topic['guidance']} Use this record when the caller "
                    f"mentions {topic['topic'].replace('_', ' ')}, region {region}, account verification "
                    f"boundaries, latency-sensitive tool routing, or supervisor review. Revision {revision} "
                    f"adds deterministic case variation for RAG benchmarking without changing the canonical "
                    f"ATX-204871 workflow account."
                ),
            }
        )
    return documents


ATENXION_RAG_DOCUMENTS = _build_atenxion_rag_documents()
