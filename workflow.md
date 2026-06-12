# 3 Minute Cost Tracking Call Workflow

Purpose: run one repeatable 3 minute call through the current Atenxion call-center workflow and capture whole-pipeline cost telemetry from the existing `metrics_update` and `cost_estimate` events.

This workflow does not require new mock data. It uses the existing demo customer in `backend/app/agents/callcenter/mock_data.py`.

## Current Data To Use

- Customer name: Htoo Thet
- Account phone number: 09661200650
- Account ID: ATX-204871
- Service address ZIP code: 98109
- Current plan: Unlimited Plus
- Latest bill: BILL-2026-04, total $146.32, prior month $97.84
- Key billing drivers already in mock data: international calls, roaming day passes, device protection, taxes and fees
- Home internet device already in mock data: ATX-GW-7781

## Run Setup

Use the current browser voice flow:

1. Start the OpenAI backend and frontend as usual.
2. Keep `VOICE_PROVIDER=cascaded_pipeline` unless you intentionally want to compare `elevenlabs_pipeline`.
3. Connect from the UI and open the Logs panel.
4. At the end of the call, expand each `metrics_update` and `cost_estimate` event.
5. Add the per-turn values together to estimate the full 3 minute call cost.

The important event fields are:

- `metrics_update.usage.input_audio_minutes`
- `metrics_update.usage.output_audio_minutes`
- `metrics_update.usage.llm_input_tokens_est`
- `metrics_update.usage.llm_output_tokens_est`
- `metrics_update.usage.tts_characters`
- `cost_estimate.stt_usd_est`
- `cost_estimate.llm_usd_est`
- `cost_estimate.elevenlabs_credits_est`
- `cost_estimate.total_usd_est_excluding_elevenlabs_subscription`

## Operator Timing

Keep each caller turn short and natural. Wait for the assistant to finish speaking before the next prompt unless the goal is to test barge-in separately.

Target call length: about 3 minutes.

Recommended pacing:

- 0:00-0:25: greeting and reason for call
- 0:25-0:55: verification
- 0:55-1:35: billing explanation
- 1:35-2:05: payment or credit question
- 2:05-2:35: technical support side question
- 2:35-3:00: retention/closure question

## 3 Minute Caller Script

### Turn 1: Open With Billing Intent

Approx time: 0:00

Say:

> Hi, I am calling because my latest Atenxion bill is much higher than normal, and I want to understand what changed.

Expected workflow:

- `callcenteragent` should identify a billing issue.
- The agent should ask for the phone number before account-specific details.
- Watch for `history_added`, `stt_final`, and eventually a tool event for lookup or verification.

### Turn 2: Verify Existing Customer

Approx time: 0:25

Say:

> The phone number on the account is 09661200650.

Expected workflow:

- `verifyCaller` should pass.
- The call should hand off to `billingAgent`.
- Watch for `tool_start`, `tool_end`, `handoff`, `agent_speech_start`, transfer audio events, and `metrics_update`.

### Turn 3: Ask For Bill Breakdown

Approx time: 0:55

Say:

> Can you compare this bill against my previous month and explain the main reason it went up?

Expected workflow:

- `billingAgent` should use billing tools before explaining.
- Existing bill data should drive the answer:
  - current bill: $146.32
  - prior month: $97.84
  - likely drivers: international calls and roaming day passes
- Watch for `getLatestBill` and `explainChargeBreakdown` tool events.

### Turn 4: Ask For Payment Flexibility Or Credit

Approx time: 1:35

Say:

> That makes sense, but I was traveling and did not expect it. Is there any payment flexibility or small goodwill credit you can apply?

Expected workflow:

- `billingAgent` may check policy or use payment/credit tools.
- Existing supported outcomes include:
  - payment arrangement for $60 deferred until 2026-05-29
  - goodwill credit up to $20 when appropriate
- Watch for `offerPaymentArrangement`, `applyGoodwillCredit`, and a new `metrics_update`.

### Turn 5: Add A Home Internet Issue

Approx time: 2:05

Say:

> One more thing, my home internet has been dropping today at my service address. Can you check whether there is an outage or device issue?

Expected workflow:

- The system should transfer to `technicalSupportAgent`.
- Technical support should use outage or diagnostics tools.
- Existing mock data supports:
  - ZIP code 98109
  - home internet service
  - modem ID ATX-GW-7781
  - area outage check for home internet in 98109
- Watch for `checkServiceOutage`, possible `runLineDiagnostics`, handoff events, and another `metrics_update`.

### Turn 6: Retention/Closure Pressure

Approx time: 2:35

Say:

> If both my bill and internet keep being a problem, I may need a cheaper plan or I might cancel. What option do I have?

Expected workflow:

- The system should transfer to `retentionAgent`.
- Retention can use plan and offer tools.
- Existing mock data supports:
  - current plan: Unlimited Plus at $89
  - lower-cost plan: Atenxion Start at $55
  - retention offer: $15 monthly discount for 3 months
- Watch for `lookupPlanOptions`, `comparePlans`, `generateRetentionOffer`, handoff events, and final `metrics_update`.

### Turn 7: Close The Call

Approx time: 2:55

Say:

> That helps. Please note the billing explanation and the plan option, and you can close this case as resolved.

Expected workflow:

- The agent should close politely.
- Watch for final `history_added`, `audio_end`, `agent_end`, `metrics_update`, and `cost_estimate`.

## Cost Capture Sheet

After the call, copy the values from every `metrics_update` and `cost_estimate` event into this table.

| Turn | Main path | STT input minutes | TTS output minutes | LLM input tokens est | LLM output tokens est | TTS characters | STT USD est | LLM USD est | ElevenLabs credits est | Total USD est excluding ElevenLabs subscription |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Opening and verification | | | | | | | | | |
| 2 | Billing explanation | | | | | | | | | |
| 3 | Payment or goodwill | | | | | | | | | |
| 4 | Technical support handoff | | | | | | | | | |
| 5 | Retention or closure | | | | | | | | | |
| Total | Whole 3 minute call | | | | | | | | | |

## What This Scenario Covers

- Browser microphone audio to backend WebSocket
- STT path for the selected architecture
- OpenAI Agents SDK text orchestration
- Tool calls over the existing mock customer, billing, support, and retention data
- Agent handoffs and transfer audio
- ElevenLabs TTS output
- Frontend transcript and Logs panel
- Turn-level `metrics_update` and `cost_estimate` events

## Notes For Repeatability

- Do not change the phone number unless you intentionally want a failed-verification test.
- Do not introduce a new customer name, account number, service address, or bill amount.
- Keep the call close to 3 minutes by waiting for each assistant response, then moving to the next scripted prompt.
- If the assistant asks a clarifying question, answer using only the existing data listed at the top of this file.
- If you are comparing models, keep the same script and only change the model environment variable before rebuilding or restarting the backend.
