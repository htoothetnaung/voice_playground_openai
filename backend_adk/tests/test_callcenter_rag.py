"""Tests for Atenxion vector-store RAG helpers."""

import pytest

from app.agents.callcenter.tools import (
    _build_vector_store_search_payload,
    _search_atenxion_knowledge_base_impl,
)
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    defaults = {
        "OPENAI_API_KEY": "sk-test",
        "CALLCENTER_RAG_VECTOR_STORE_ID": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeVectorStoreClient:
    def __init__(self) -> None:
        self.requests = []
        self.vector_stores = FakeVectorStores(self)


class FakeVectorStores:
    def __init__(self, client: FakeVectorStoreClient) -> None:
        self.client = client

    def search(self, vector_store_id, **body):
        self.client.requests.append({"vector_store_id": vector_store_id, "body": body})
        return FakeSearchPaginator(
            [
                {
                    "file_id": "file_123",
                    "filename": "atenxion-goodwill-credit-billing.md",
                    "score": 0.92,
                    "attributes": {
                        "topic": "goodwill_credit",
                        "service_type": "billing",
                    },
                    "content": [
                        {
                            "type": "text",
                            "text": "Frontline credits above authority require supervisor approval.",
                        }
                    ],
                }
            ]
        )


class FakeSearchPaginator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_rag_tool_impl_reports_missing_vector_store_id() -> None:
    result = await _search_atenxion_knowledge_base_impl(
        _settings(),
        query="goodwill credit",
    )

    assert result["available"] is False
    assert "CALLCENTER_RAG_VECTOR_STORE_ID" in result["reason"]
    assert result["results"] == []


def test_vector_store_search_payload_clamps_and_filters() -> None:
    payload = _build_vector_store_search_payload(
        query="roaming exception",
        max_num_results=99,
        topic="goodwill_credit",
        service_type="billing",
    )

    assert payload["max_num_results"] == 50
    assert payload["rewrite_query"] is True
    assert payload["filters"] == {
        "type": "and",
        "filters": [
            {"type": "eq", "key": "topic", "value": "goodwill_credit"},
            {"type": "eq", "key": "service_type", "value": "billing"},
        ],
    }


@pytest.mark.asyncio
async def test_rag_tool_impl_normalizes_vector_store_results() -> None:
    client = FakeVectorStoreClient()

    result = await _search_atenxion_knowledge_base_impl(
        _settings(CALLCENTER_RAG_VECTOR_STORE_ID="vs_test"),
        query="Find roaming goodwill policy",
        max_num_results=3,
        topic="goodwill_credit",
        service_type="billing",
        client=client,
    )

    assert result["available"] is True
    assert result["result_count"] == 1
    assert result["results"][0]["filename"] == "atenxion-goodwill-credit-billing.md"
    assert result["results"][0]["attributes"]["topic"] == "goodwill_credit"
    assert "supervisor approval" in result["results"][0]["snippets"][0]
    assert result["latency_ms"] >= 0
    assert client.requests[0]["vector_store_id"] == "vs_test"
    assert client.requests[0]["body"]["max_num_results"] == 3
