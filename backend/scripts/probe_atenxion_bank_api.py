"""Probe the Atenxion Bank QA transaction endpoint with configured settings."""

from __future__ import annotations

import asyncio
import json

from app.agents.callcenter.bank_tool import fetch_atenxion_bank_transactions
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    result = await fetch_atenxion_bank_transactions(
        settings,
        user_id=settings.atenxion_bank_test_user_id,
    )
    keys = [
        "available",
        "status_code",
        "msg",
        "reason",
        "transaction_count",
        "credit_count",
        "debit_count",
        "latency_ms",
        "user_id",
    ]
    print(json.dumps({key: result.get(key) for key in keys}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
