# MCP Implementation Explanation

## Short Answer

This project currently uses **OpenAI Responses API MCP tools**, not the Agents SDK `MCPServer*` classes.

That means the implementation does **not** instantiate:

- `MCPServerStdio`
- `MCPServerSse`
- `MCPServerStreamableHttp`

Instead, the backend builds normal Responses API tool definitions shaped like:

```json
{
  "type": "mcp",
  "connector_id": "connector_gmail"
}
```

or:

```json
{
  "type": "mcp",
  "server_url": "https://your-trusted-ticketing-mcp.example.com/sse"
}
```

Those tool definitions are sent through `client.responses.create(...)`.

## Why It Was Implemented This Way

The current call-center backend is built around the OpenAI Agents SDK `function_tool` pattern. To keep that architecture stable, the live agents still receive ordinary Python function tools such as:

- `search_gmail_customer_history`
- `send_customer_followup_email_via_mcp`
- `search_customer_tickets_via_mcp`
- `create_customer_ticket_via_mcp`

Inside those tools, the backend makes a Responses API call with the built-in MCP tool type.

So the layering is:

```text
Call-center agent
  -> OpenAI Agents SDK function_tool
    -> backend Python helper
      -> OpenAI Responses API
        -> connector_id or server_url MCP tool
          -> Gmail connector / remote MCP server
```

This keeps the existing graph, realtime runtime, tool traces, and stress-lab patterns intact.

## Connector vs Remote MCP Server

### Gmail

Gmail is implemented as an **OpenAI connector**:

```python
{
    "type": "mcp",
    "server_label": "gmail",
    "connector_id": "connector_gmail",
    "authorization": settings.mcp_gmail_oauth_token,
    "require_approval": settings.mcp_gmail_require_approval,
    "allowed_tools": [...]
}
```

This lives in:

```text
backend/app/agents/callcenter/mcp_integrations.py
```

Important limitation from the official docs:

The Gmail connector exposes read/search style tools, including:

- `get_profile`
- `search_emails`
- `search_email_ids`
- `get_recent_emails`
- `read_email`
- `batch_read_email`

It does **not** expose a send-email tool in the docs we checked.

So Gmail is currently useful for searching customer email history, not sending support emails.

### Customer Email Sending

Customer follow-up email sending is implemented as a **remote MCP server placeholder**, not as Gmail.

It uses:

```python
{
    "type": "mcp",
    "server_label": "customer_email_mcp",
    "server_url": settings.mcp_email_server_url,
    "authorization": settings.mcp_email_authorization,
    "allowed_tools": ["send_email", "send_message", "create_draft"],
    "require_approval": settings.mcp_email_require_approval,
    "defer_loading": True
}
```

This expects you to provide a trusted email MCP server URL through:

```text
MCP_EMAIL_SERVER_URL
```

If the future email MCP server is private, it can be exposed through OpenAI Secure MCP Tunnel, but this repo does not currently start or manage the tunnel client.

### Zendesk / Zoho Desk / Ticketing

Ticketing is also implemented as a **remote MCP server placeholder**.

It uses:

```python
{
    "type": "mcp",
    "server_label": "customer_ticketing_mcp",
    "server_url": settings.mcp_ticketing_server_url,
    "authorization": settings.mcp_ticketing_authorization,
    "allowed_tools": ["search_tickets", "create_ticket", "update_ticket", "add_comment"],
    "require_approval": settings.mcp_ticketing_require_approval,
    "defer_loading": True
}
```

This is intended for a trusted Zendesk, Zoho Desk, or similar customer-service MCP server once you choose one.

## Transport Type

Because this implementation uses the Responses API MCP tool, the backend does not directly choose an Agents SDK server class.

The transport is inferred by the MCP server URL and supported by the Responses API.

From the official local docs:

- Remote MCP servers can use **Streamable HTTP**
- Remote MCP servers can use **HTTP/SSE**
- Connectors use `connector_id`, not `server_url`

In our env sample, the placeholder URLs use `/sse`, which implies an HTTP/SSE style remote MCP endpoint:

```text
MCP_EMAIL_SERVER_URL=https://your-trusted-email-mcp.example.com/sse
MCP_TICKING_SERVER_URL=https://your-zendesk-or-zoho-mcp.example.com/sse
```

If you later provide a Streamable HTTP server URL, the same Responses API `server_url` field is still the integration point.

## Secure MCP Tunnel

Secure MCP Tunnel is **not currently implemented in repo code**.

The code is tunnel-compatible in the sense that `MCP_EMAIL_SERVER_URL` and `MCP_TICKETING_SERVER_URL` can point to a URL produced by a tunnel setup.

But the repo does not currently:

- download the tunnel client
- start the tunnel client
- manage tunnel lifecycle
- store tunnel config

That should be a separate implementation step once we know which private MCP server we are exposing.

## Safety Defaults

The default config uses approval-required behavior:

```text
MCP_GMAIL_REQUIRE_APPROVAL=always
MCP_EMAIL_REQUIRE_APPROVAL=always
MCP_TICKETING_REQUIRE_APPROVAL=always
```

The tools also avoid claiming success unless the Responses API result shows an actual MCP call completed without approval pending or errors.

For example, `send_customer_followup_email_via_mcp` returns:

```python
"sent": bool(result["mcp_call_count"] and not result["approval_required"] and not result["errors"])
```

So if the model produces an `mcp_approval_request`, the agent should say the action needs approval rather than claiming the email was sent.

## Files Changed

Main MCP helper:

```text
backend/app/agents/callcenter/mcp_integrations.py
```

Live workflow tools:

```text
backend/app/agents/callcenter/tools.py
```

Agent wiring:

```text
backend/app/agents/callcenter/graph.py
backend/app/agents/callcenter/realtime_graph.py
```

Stress Lab scenarios:

```text
backend/app/agents/callcenter/stress_lab.py
src/app/stress-lab/page.tsx
```

Config:

```text
backend/app/core/config.py
.env.sample
```

Tests:

```text
backend/tests/test_callcenter_mcp_tools.py
backend/tests/test_stress_lab.py
backend/tests/test_callcenter_metadata.py
```
