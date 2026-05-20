# Atenxion Bank Tool Implementation

## What Was Added

This implementation adds an OpenAI Agents SDK function tool with the callable schema name `atenxion_bank_tool` to the existing `backend` service. It keeps `Atenxion-bank-tool` as the display label in route metadata and tool results. It does not touch `backend_adk`.

The tool calls the documented Atenxion Bank OpenAPI endpoint directly:

```text
POST https://api-qabank.atenxion.ai/api/v1/transaction/get-details
```

Request body:

```json
{
  "userId": "6a0d6b143cac1525e1e4ce87"
}
```

## Framework Path

This is not MCP and it is not a connector.

It is a normal OpenAI Agents SDK `@function_tool` with `name_override="atenxion_bank_tool"`. The backend implementation uses `httpx.AsyncClient` to call the Atenxion Bank REST API. That is similar in spirit to Google ADK/OpenAPI-style tools because the agent tool is a thin wrapper around a typed external HTTP API, but it remains inside the current OpenAI Agents SDK backend.

The first implementation exposed the literal hyphenated label `Atenxion-bank-tool` as the callable tool name. That was changed because the voice/runtime path can surface `unknown_tool` or make model tool selection less reliable when the callable name is not a normal function-style identifier. The agent now calls `atenxion_bank_tool`; user-facing metadata can still say `Atenxion-bank-tool`.

## Runtime Integration

The shared HTTP client lives in:

```text
backend/app/agents/callcenter/bank_tool.py
```

The callable agent tool lives in:

```text
backend/app/agents/callcenter/tools.py
```

The tool is wired into:

- `billingAgent`, for transaction/payment-history questions.
- `supervisorAgent`, for escalated transaction fact checks.
- `humanEscalationAgent`, for escalated caller workflows.
- The OpenAI Realtime graph, so the native voice workflow can expose the same tool.
- The cascaded voice workflow, because it builds from the same non-realtime agent graph.

The tool keeps the existing account-safety style: it returns `verification_required` unless `CallCenterContext.verified` is true.

## Stress Lab Integration

Stress Lab now has a scenario:

```text
atenxion_bank_transaction_lookup
```

It appears as an `external_api_tool` scenario and records:

- total scenario latency
- bank API latency
- HTTP status code
- payload size
- transaction count
- credit/debit counts

The frontend stress-lab filter now includes `External API`.

## Configuration

New environment variables:

```text
ATENXION_BANK_API_BASE_URL=https://api-qabank.atenxion.ai
ATENXION_BANK_API_TOKEN=
ATENXION_BANK_TEST_USER_ID=6a0d6b143cac1525e1e4ce87
ATENXION_BANK_TIMEOUT_SECONDS=10
```

If `ATENXION_BANK_API_TOKEN` is set, the client sends:

```text
Authorization: Bearer <token>
```

If it is blank, the client still attempts the request. The current QA endpoint returned HTTP 200 without a token during verification.

## Verification Result

The real QA probe returned:

```json
{
  "available": true,
  "status_code": 200,
  "msg": "Success",
  "transaction_count": 0,
  "credit_count": 0,
  "debit_count": 0,
  "user_id": "6a0d6b143cac1525e1e4ce87"
}
```

So the endpoint is reachable and responding successfully for the requested user ID. The response currently contains no transaction rows for that QA user.
