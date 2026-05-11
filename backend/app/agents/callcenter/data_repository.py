"""Reads call-center demo records from MongoDB with in-code mock data as fallback."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.agents.callcenter.mock_data import (
    ATENXION_ACTIVE_SERVICES,
    ATENXION_CUSTOMER_PROFILE,
    ATENXION_LATEST_BILL,
    ATENXION_PLAN_CATALOG,
    ATENXION_POLICY_DOCS,
)
from app.core.config import Settings, get_settings
from app.core.mongo import get_mongo_database

MOCK_DATA_COLLECTIONS = {
    "customer_profiles": [ATENXION_CUSTOMER_PROFILE],
    "active_services": [ATENXION_ACTIVE_SERVICES],
    "latest_bills": [ATENXION_LATEST_BILL],
    "plan_catalog": ATENXION_PLAN_CATALOG,
    "policy_docs": ATENXION_POLICY_DOCS,
}
_UNSET = object()


def _strip_mongo_id(value: Any) -> Any:
    """Remove Mongo ObjectIds from records returned to model tools."""
    if isinstance(value, dict):
        return {key: _strip_mongo_id(val) for key, val in value.items() if key != "_id"}
    if isinstance(value, list):
        return [_strip_mongo_id(item) for item in value]
    return value


class CallCenterDataRepository:
    """Fetch seedable mock records from MongoDB and fall back to constants on any miss."""

    def __init__(self, settings: Settings | None = None, db: Any = _UNSET) -> None:
        self.settings = settings
        if db is not _UNSET:
            self.db = db
        else:
            self.settings = settings or get_settings()
            self.db = get_mongo_database(self.settings)

    async def seed_mock_data(self) -> bool:
        """Upsert the current demo records into MongoDB collections."""
        if self.db is None:
            return False
        try:
            for collection_name, records in MOCK_DATA_COLLECTIONS.items():
                collection = self.db[collection_name]
                for record in records:
                    identity = _record_identity(collection_name, record)
                    await collection.update_one(identity, {"$set": deepcopy(record)}, upsert=True)
            return True
        except Exception:
            return False

    async def customer_profile(self) -> dict[str, Any]:
        record = await self._find_one("customer_profiles", {})
        return record or deepcopy(ATENXION_CUSTOMER_PROFILE)

    async def active_services(self) -> dict[str, Any]:
        record = await self._find_one("active_services", {})
        return record or deepcopy(ATENXION_ACTIVE_SERVICES)

    async def latest_bill(self) -> dict[str, Any]:
        record = await self._find_one("latest_bills", {})
        return record or deepcopy(ATENXION_LATEST_BILL)

    async def plan_catalog(self) -> list[dict[str, Any]]:
        records = await self._find_many("plan_catalog")
        return records or deepcopy(ATENXION_PLAN_CATALOG)

    async def policy_docs(self) -> list[dict[str, Any]]:
        records = await self._find_many("policy_docs")
        return records or deepcopy(ATENXION_POLICY_DOCS)

    async def _find_one(self, collection_name: str, query: dict[str, Any]) -> dict[str, Any] | None:
        if self.db is None:
            return None
        try:
            record = await self.db[collection_name].find_one(query)
        except Exception:
            return None
        return _strip_mongo_id(record) if record else None

    async def _find_many(self, collection_name: str) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        try:
            cursor = self.db[collection_name].find({})
            records = await cursor.to_list(length=None)
        except Exception:
            return []
        return [_strip_mongo_id(record) for record in records]


def _record_identity(collection_name: str, record: dict[str, Any]) -> dict[str, Any]:
    if collection_name == "customer_profiles":
        return {"account_id": record["account_id"]}
    if collection_name == "active_services":
        return {"_seed_key": "default_active_services"}
    if collection_name == "latest_bills":
        return {"bill_id": record["bill_id"]}
    if collection_name == "plan_catalog":
        return {"code": record["code"]}
    if collection_name == "policy_docs":
        return {"id": record["id"]}
    return record
