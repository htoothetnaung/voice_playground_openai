"""HTTP client helpers for Atenxion Bank transaction lookup tools."""

from __future__ import annotations

from time import monotonic
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings

ATENXION_BANK_TOOL_NAME = "atenxion_bank_tool"
ATENXION_BANK_TOOL_DISPLAY_NAME = "Atenxion-bank-tool"
ATENXION_BANK_TRANSACTION_PATH = "/api/v1/transaction/get-details"


class AtenxionBankTransactionRequest(BaseModel):
    """Request body for the Atenxion Bank transaction details endpoint."""

    userId: str = Field(
        description="Unique identifier of the user to retrieve transaction details for. Required."
    )


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _summarize_transactions(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    credit_total = 0.0
    debit_total = 0.0
    for transaction in transactions:
        amount = float(transaction.get("amount") or 0)
        if transaction.get("isCredit"):
            credit_total += amount
        else:
            debit_total += amount
    return {
        "transaction_count": len(transactions),
        "credit_count": sum(1 for item in transactions if item.get("isCredit")),
        "debit_count": sum(1 for item in transactions if not item.get("isCredit")),
        "total_credit": round(credit_total, 2),
        "total_debit": round(debit_total, 2),
    }


async def fetch_atenxion_bank_transactions(
    settings: Settings,
    *,
    user_id: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch completed transaction details for a user from the Atenxion Bank API."""
    request = AtenxionBankTransactionRequest(userId=user_id)
    url = f"{_normalize_base_url(settings.atenxion_bank_api_base_url)}{ATENXION_BANK_TRANSACTION_PATH}"
    headers = {"Content-Type": "application/json"}
    if settings.atenxion_bank_api_token:
        headers["Authorization"] = f"Bearer {settings.atenxion_bank_api_token}"

    start = monotonic()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.atenxion_bank_timeout_seconds)
    try:
        response = await active_client.post(
            url,
            json=request.model_dump(),
            headers=headers,
        )
        elapsed_ms = round((monotonic() - start) * 1000, 3)
        try:
            decoded = response.json()
            payload = decoded if isinstance(decoded, dict) else {"data": decoded}
        except ValueError:
            payload = {"raw_text": response.text[:1000]}

        transactions = payload.get("data") if isinstance(payload.get("data"), list) else []
        normalized = {
            "available": response.status_code == 200,
            "tool_name": ATENXION_BANK_TOOL_NAME,
            "tool_display_name": ATENXION_BANK_TOOL_DISPLAY_NAME,
            "provider": "atenxion_bank",
            "status_code": response.status_code,
            "user_id": user_id,
            "latency_ms": elapsed_ms,
            "msg": payload.get("msg"),
            "data": transactions,
            **_summarize_transactions(transactions),
        }
        if response.status_code != 200:
            normalized["reason"] = (
                payload.get("error")
                or payload.get("message")
                or payload.get("raw_text")
                or f"Atenxion Bank API returned HTTP {response.status_code}."
            )
        return normalized
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "tool_name": ATENXION_BANK_TOOL_NAME,
            "tool_display_name": ATENXION_BANK_TOOL_DISPLAY_NAME,
            "provider": "atenxion_bank",
            "status_code": None,
            "user_id": user_id,
            "latency_ms": round((monotonic() - start) * 1000, 3),
            "reason": f"{type(exc).__name__}: {exc}",
            "data": [],
            "transaction_count": 0,
            "credit_count": 0,
            "debit_count": 0,
            "total_credit": 0,
            "total_debit": 0,
        }
    finally:
        if owns_client:
            await active_client.aclose()
