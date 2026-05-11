"""Serializes SDK/provider objects and builds audio/history message payloads sent over the backend WebSocket."""

from __future__ import annotations

import base64
from dataclasses import asdict, is_dataclass
from typing import Any


def serialize(value: Any) -> Any:
    """Convert SDK/provider objects into JSON-safe values for cascaded WebSocket events."""
    if is_dataclass(value):
        return {key: serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): serialize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("utf-8")
    if hasattr(value, "model_dump"):
        return serialize(value.model_dump())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {
            key: serialize(val)
            for key, val in vars(value).items()
            if not key.startswith("_")
        }
    return value


def audio_event(
    item_id: str,
    content_index: int,
    audio_bytes: bytes,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Build the frontend audio event payload with base64 PCM data and optional speaking agent name."""
    event = {
        "type": "audio",
        "item_id": item_id,
        "content_index": content_index,
        "data": base64.b64encode(audio_bytes).decode("utf-8"),
    }
    if agent_name:
        event["agent_name"] = agent_name
    return event


def message_item(item_id: str, role: str, text: str) -> dict[str, Any]:
    """Build a conversation history item compatible with the frontend transcript schema."""
    return {
        "id": item_id,
        "item_id": item_id,
        "type": "message",
        "role": role,
        "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
    }
