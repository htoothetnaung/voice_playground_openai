"""Shared helpers for OpenAI Responses MCP connector and remote MCP calls."""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings

MCP_DOC_SUMMARY = (
    "OpenAI Responses MCP tools support connectors through connector_id and remote MCP "
    "servers through server_url. The official Gmail connector currently exposes read/search "
    "tools, not a send-email tool, so sending mail requires a trusted remote MCP email server."
)


def csv_values(raw: str | None) -> list[str]:
    """Parse comma-separated config values."""
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def validate_email(value: str) -> bool:
    """Lightweight validation for user-provided email recipients."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def gmail_connector_tool(settings: Settings) -> dict[str, Any] | None:
    """Build the official Gmail connector MCP tool config when OAuth is configured."""
    if not settings.mcp_gmail_oauth_token:
        return None
    return {
        "type": "mcp",
        "server_label": "gmail",
        "connector_id": "connector_gmail",
        "authorization": settings.mcp_gmail_oauth_token,
        "require_approval": settings.mcp_gmail_require_approval,
        "allowed_tools": [
            "get_profile",
            "search_emails",
            "search_email_ids",
            "get_recent_emails",
            "read_email",
            "batch_read_email",
        ],
    }


def remote_email_tool(settings: Settings) -> dict[str, Any] | None:
    """Build the remote MCP email server config used for drafts or sending."""
    if not settings.mcp_email_server_url:
        return None
    return _remote_tool(
        server_label="customer_email_mcp",
        server_description=(
            "Trusted customer communications MCP server for drafting or sending support "
            "follow-up emails after an Atenxion call."
        ),
        server_url=settings.mcp_email_server_url,
        authorization=settings.mcp_email_authorization,
        allowed_tools=csv_values(settings.mcp_email_allowed_tools_raw),
        require_approval=settings.mcp_email_require_approval,
        defer_loading=True,
    )


def remote_ticketing_tool(settings: Settings) -> dict[str, Any] | None:
    """Build the remote MCP ticketing config for future Zoho Desk or Zendesk-style systems."""
    if not settings.mcp_ticketing_server_url:
        return None
    return _remote_tool(
        server_label="customer_ticketing_mcp",
        server_description=(
            "Trusted customer-service platform MCP server for searching, creating, updating, "
            "and commenting on complaint tickets in systems such as Zendesk or Zoho Desk."
        ),
        server_url=settings.mcp_ticketing_server_url,
        authorization=settings.mcp_ticketing_authorization,
        allowed_tools=csv_values(settings.mcp_ticketing_allowed_tools_raw),
        require_approval=settings.mcp_ticketing_require_approval,
        defer_loading=True,
    )


def _remote_tool(
    *,
    server_label: str,
    server_description: str,
    server_url: str,
    authorization: str | None,
    allowed_tools: list[str],
    require_approval: str,
    defer_loading: bool,
) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "type": "mcp",
        "server_label": server_label,
        "server_description": server_description,
        "server_url": server_url,
        "require_approval": require_approval,
        "defer_loading": defer_loading,
    }
    if authorization:
        tool["authorization"] = authorization
    if allowed_tools:
        tool["allowed_tools"] = allowed_tools
    return tool


async def run_mcp_response(
    client: AsyncOpenAI,
    settings: Settings,
    *,
    tool_name: str,
    tool: dict[str, Any],
    input_text: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Run one Responses API call with a single MCP connector or remote server tool."""
    response = await client.responses.create(
        model=model or settings.responses_model,
        tools=[tool],
        tool_choice="required",
        input=input_text,
    )
    dumped = response.model_dump() if hasattr(response, "model_dump") else response
    output_items = dumped.get("output", []) if isinstance(dumped, dict) else []
    return normalize_mcp_output(tool_name, tool, output_items)


def normalize_mcp_output(
    tool_name: str,
    tool: dict[str, Any],
    output_items: list[Any],
) -> dict[str, Any]:
    """Return compact, reviewable MCP metadata without storing large raw third-party payloads."""
    typed_items = [item for item in output_items if isinstance(item, dict)]
    item_types = [str(item.get("type")) for item in typed_items]
    list_tools_items = [item for item in typed_items if item.get("type") == "mcp_list_tools"]
    mcp_calls = [item for item in typed_items if item.get("type") == "mcp_call"]
    approvals = [item for item in typed_items if item.get("type") == "mcp_approval_request"]
    errors = [call.get("error") for call in mcp_calls if call.get("error")]
    allowed_tools = tool.get("allowed_tools") or []
    imported_tools = [
        imported.get("name")
        for item in list_tools_items
        for imported in item.get("tools", [])
        if isinstance(imported, dict)
    ]
    return {
        "available": True,
        "tool_name": tool_name,
        "server_label": tool.get("server_label"),
        "connector_id": tool.get("connector_id"),
        "server_url_configured": bool(tool.get("server_url")),
        "allowed_tools": allowed_tools,
        "output_item_count": len(output_items),
        "output_item_types": item_types,
        "imported_tools": imported_tools[:12],
        "mcp_call_count": len(mcp_calls),
        "approval_required": bool(approvals),
        "approval_request_count": len(approvals),
        "errors": errors,
        "output_preview": _preview_calls(mcp_calls),
    }


def _preview_calls(mcp_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previews = []
    for call in mcp_calls[:3]:
        output = call.get("output")
        if isinstance(output, str):
            preview = output[:500]
        else:
            preview = json.dumps(output, sort_keys=True)[:500]
        previews.append(
            {
                "name": call.get("name"),
                "server_label": call.get("server_label"),
                "has_error": bool(call.get("error")),
                "output_preview": preview,
            }
        )
    return previews
