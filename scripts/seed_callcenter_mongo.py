"""Seed the Atenxion call-center mock data into the configured MongoDB database."""
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.callcenter.data_repository import CallCenterDataRepository
from app.core.config import get_settings


async def main() -> int:
    settings = get_settings()
    seeded = await CallCenterDataRepository(settings).seed_mock_data()
    if not seeded:
        print(
            "MongoDB seed skipped or failed. Ensure MongoDB is running at "
            f"{settings.mongodb_uri}."
        )
        return 1
    print(f"Seeded call-center mock data into {settings.mongodb_db}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
