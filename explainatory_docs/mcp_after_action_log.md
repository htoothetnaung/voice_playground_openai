# MCP After-Implementation Log

## 1. Gmail Customer History

### What Was Implemented

Added a live workflow tool:

```text
search_gmail_customer_history
```

### What MCP Type It Uses

This uses an **OpenAI connector**, not a raw MCP server.

It passes:

```text
connector_id=connector_gmail
```

It does not use:

- `MCPServerStdio`
- `MCPServerSse`
- `MCPServerStreamableHttp`

### Why

The official OpenAI docs list Gmail as an available connector. The listed Gmail tools are read/search tools, so this fits customer email history lookup.

### Current Config

```text
MCP_GMAIL_OAUTH_TOKEN=...
MCP_GMAIL_REQUIRE_APPROVAL=always
```

## 2. Customer Follow-Up Email

### What Was Implemented

Added a live workflow tool:

```text
send_customer_followup_email_via_mcp
```

### What MCP Type It Uses

This uses a **remote MCP server through Responses API `server_url`**.

It does not use an official Gmail send connector because the local official docs did not list Gmail send-email capability.

It does not directly use:

- `MCPServerStdio`
- `MCPServerSse`
- `MCPServerStreamableHttp`

### Expected Remote Server

The configured server should expose at least one allowed tool such as:

```text
send_email
send_message
create_draft
```

### Current Config

```text
MCP_EMAIL_SERVER_URL=https://your-trusted-email-mcp.example.com/sse
MCP_EMAIL_AUTHORIZATION=...
MCP_EMAIL_ALLOWED_TOOLS=send_email,send_message,create_draft
MCP_EMAIL_REQUIRE_APPROVAL=always
```

### Tunnel Status

Secure MCP Tunnel is not currently managed by this repo. If the email MCP server is private, point `MCP_EMAIL_SERVER_URL` at the tunneled public endpoint after configuring the tunnel separately.

## 3. Customer Ticketing

### What Was Implemented

Added live workflow tools:

```text
search_customer_tickets_via_mcp
create_customer_ticket_via_mcp
```

### What MCP Type It Uses

This uses a **remote MCP server through Responses API `server_url`**.

This is the future integration path for Zendesk, Zoho Desk, or another customer service platform.

### Expected Remote Server

The configured server should expose allowed tools such as:

```text
search_tickets
create_ticket
update_ticket
add_comment
```

### Current Config

```text
MCP_TICKETING_SERVER_URL=https://your-zendesk-or-zoho-mcp.example.com/sse
MCP_TICKETING_AUTHORIZATION=...
MCP_TICKETING_ALLOWED_TOOLS=search_tickets,create_ticket,update_ticket,add_comment
MCP_TICKETING_REQUIRE_APPROVAL=always
```

### Tunnel Status

Secure MCP Tunnel is not currently managed by this repo. If Zendesk or Zoho Desk access is exposed through an internal MCP server, the tunnel can be added later.

## 4. Stress Lab MCP Scenarios

### What Was Implemented

Added three new Stress Lab scenarios:

```text
openai_mcp_gmail_customer_history
openai_mcp_customer_email_followup
openai_mcp_customer_ticketing
```

### What They Measure

They measure the Responses API MCP path:

```text
Responses API -> mcp list/call/approval output items -> normalized benchmark result
```

They record compact metadata such as:

- server label
- connector id
- allowed tools
- output item types
- MCP call count
- approval required
- payload size
- duration

They do not store full third-party email or ticket payloads.

## 5. What Is Still Not Implemented

The following are intentionally not implemented yet:

- An actual Zendesk MCP server
- An actual Zoho Desk MCP server
- An actual email-sending MCP server
- Secure MCP Tunnel lifecycle management
- Agents SDK direct `MCPServer*` classes
- Human approval UI for `mcp_approval_request`

The current implementation is ready to call configured connector/server URLs, but real action depends on credentials and a trusted MCP server being provided.
