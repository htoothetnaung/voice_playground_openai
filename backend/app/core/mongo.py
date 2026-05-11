"""Optional MongoDB connection helpers used by the call-center demo."""
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - exercised when Mongo extras are not installed.
    AsyncIOMotorClient = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def get_mongo_client(uri: str | None = None) -> Any | None:
    """Return a cached Motor client, or None when the optional dependency is unavailable."""
    if AsyncIOMotorClient is None:
        return None
    settings = get_settings()
    return AsyncIOMotorClient(uri or settings.mongodb_uri, serverSelectionTimeoutMS=700)


def get_mongo_database(settings: Settings | None = None) -> Any | None:
    """Return the configured Mongo database handle without forcing the server to exist yet."""
    resolved_settings = settings or get_settings()
    client = get_mongo_client(resolved_settings.mongodb_uri)
    if client is None:
        return None
    return client[resolved_settings.mongodb_db]
