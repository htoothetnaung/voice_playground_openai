export const atenxionCustomerProfile = {
  account_id: 'ATX-204871',
  full_name: 'Maya Thompson',
  phone_number: '(206) 555-0147',
  date_of_birth: '1991-08-19',
  pin_last4: '4821',
  sentiment: 'frustrated_but_cooperative',
  tenure_years: 4,
  autopay: true,
  preferred_contact: 'sms',
  service_address: {
    street: '1428 Aurora Avenue N',
    city: 'Seattle',
    state: 'WA',
    postal_code: '98109',
  },
  billing_address: {
    street: '1428 Aurora Avenue N',
    city: 'Seattle',
    state: 'WA',
    postal_code: '98109',
  },
  current_plan: {
    code: 'ATX-UNLIMITED-PLUS',
    name: 'Unlimited Plus',
    monthly_price_usd: 89,
  },
  active_lines: [
    {
      line_id: 'LINE-01',
      phone_number: '(206) 555-0147',
      device_id: 'DEV-IPH15-MAYA',
      service_type: 'mobile',
    },
    {
      line_id: 'LINE-02',
      phone_number: '(206) 555-0199',
      device_id: 'DEV-IPAD-AIR',
      service_type: 'tablet',
    },
  ],
};

export const atenxionActiveServices = {
  account_id: atenxionCustomerProfile.account_id,
  services: [
    {
      service_id: 'SRV-MOB-01',
      type: '5g_mobile',
      status: 'active',
      line_id: 'LINE-01',
      plan_code: 'ATX-UNLIMITED-PLUS',
    },
    {
      service_id: 'SRV-TAB-01',
      type: 'tablet_data',
      status: 'active',
      line_id: 'LINE-02',
      plan_code: 'ATX-TAB-10GB',
    },
    {
      service_id: 'SRV-HOME-01',
      type: 'home_internet',
      status: 'active',
      speed_tier: '1 Gig',
      modem_id: 'ATX-GW-7781',
    },
  ],
};

export const atenxionLatestBill = {
  bill_id: 'BILL-2026-04',
  billing_period: '2026-04-01 to 2026-04-30',
  due_date: '2026-05-15',
  status: 'due',
  total_usd: 146.32,
  prior_month_usd: 97.84,
  summary: {
    base_plan_usd: 89,
    international_calls_usd: 22.14,
    roaming_day_passes_usd: 18,
    device_protection_usd: 12.99,
    taxes_and_fees_usd: 4.19,
  },
};

export const atenxionPlanCatalog = [
  {
    code: 'ATX-START',
    name: 'Atenxion Start',
    monthly_price_usd: 55,
    highlights: ['Unlimited talk and text', '30GB premium data', 'No hotspot'],
  },
  {
    code: 'ATX-UNLIMITED-PLUS',
    name: 'Unlimited Plus',
    monthly_price_usd: 89,
    highlights: ['Unlimited premium data', '20GB hotspot', 'International roaming perks'],
  },
  {
    code: 'ATX-FAMILY-FLEX',
    name: 'Family Flex',
    monthly_price_usd: 135,
    highlights: ['Up to 4 lines', 'Shared hotspot pool', 'Streaming bundle credit'],
  },
];

export const atenxionPolicyDocs = [
  {
    id: 'POL-001',
    topic: 'goodwill credit',
    name: 'Goodwill Credit Policy',
    content:
      'Frontline billing agents may issue up to a $20 one-time credit per rolling 12-month period when charges are valid but goodwill is appropriate. Larger credits require supervisor approval.',
  },
  {
    id: 'POL-002',
    topic: 'payment arrangement',
    name: 'Payment Flex Policy',
    content:
      'Eligible postpaid accounts in good standing may defer up to 50% of a past-due or current balance for 14 days. Accounts with repeated broken promises require supervisor review.',
  },
  {
    id: 'POL-003',
    topic: 'outage',
    name: 'Residential Outage Handling',
    content:
      'If there is a verified area outage, agents should avoid repeated troubleshooting, set expectations, and offer a case note plus optional outage-follow-up text enrollment.',
  },
  {
    id: 'POL-004',
    topic: 'retention',
    name: 'Retention Save Guidelines',
    content:
      'Retention agents may offer a three-month loyalty discount, a device protection waiver, or a downgrade path when a customer cites price pressure or cancellation intent.',
  },
  {
    id: 'POL-005',
    topic: 'technician',
    name: 'Technician Dispatch Rules',
    content:
      'Technician visits may be scheduled in 2-hour windows from 8 AM to 6 PM local time when remote diagnostics show persistent impairment or customer equipment replacement is likely.',
  },
];
