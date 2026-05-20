"""Keeps the legacy Responses proxy route available for frontend compatibility."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import AsyncOpenAI

from app.core.config import Settings, get_settings

router = APIRouter()


def get_openai_client(settings: Settings = Depends(get_settings)) -> AsyncOpenAI:
    """Create an AsyncOpenAI client with the backend API key for the Responses proxy route."""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured; the ADK backend only uses Google ADK for call-center orchestration.",
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


@router.post("/api/responses")
async def responses_proxy(
    request: Request,
    client: AsyncOpenAI = Depends(get_openai_client),
) -> Any:
    """Forward a frontend Responses API request to OpenAI and return a JSON-serializable result."""
    body = await request.json()
    try:
        if body.get("text", {}).get("format", {}).get("type") == "json_schema":
            response = await client.responses.parse(**body, stream=False)
        else:
            response = await client.responses.create(**body, stream=False)
    except Exception as exc:  # pragma: no cover - network/runtime failure path
        raise HTTPException(status_code=500, detail=f"responses_proxy_failed: {exc}") from exc

    if hasattr(response, "model_dump"):
        return response.model_dump()
    return response
