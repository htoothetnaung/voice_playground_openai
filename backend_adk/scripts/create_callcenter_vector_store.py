"""Seed Atenxion RAG data into MongoDB, then create and populate an OpenAI vector store."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from openai import OpenAI

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.callcenter.data_repository import CallCenterDataRepository
from app.core.config import get_settings


EXPORT_DIR = BACKEND_ROOT / ".data" / "vector_store_exports"
VECTOR_STORE_NAME = "atenxion-callcenter-rag"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


async def _seed_and_load_documents() -> list[dict[str, Any]]:
    settings = get_settings()
    repository = CallCenterDataRepository(settings)
    seeded = await repository.seed_mock_data()
    if not seeded:
        raise RuntimeError(
            "MongoDB seeding failed. Start MongoDB or check MONGODB_URI before creating the vector store."
        )
    return await repository.rag_documents()


def _write_grouped_markdown_files(documents: list[dict[str, Any]]) -> list[tuple[Path, dict[str, Any]]]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        grouped[(document["topic"], document["service_type"])].append(document)

    exports = []
    for (topic, service_type), records in sorted(grouped.items()):
        path = EXPORT_DIR / f"atenxion-{_slug(topic)}-{_slug(service_type)}.md"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"# Atenxion {topic.replace('_', ' ').title()} Knowledge\n\n")
            handle.write(f"Service type: {service_type}\n\n")
            for record in records:
                handle.write(f"## {record['document_id']}: {record['title']}\n\n")
                handle.write(record["content"])
                handle.write("\n\n")
                handle.write("Metadata:\n")
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True))
                handle.write("\n\n")
        exports.append(
            (
                path,
                {
                    "company": "Atenxion",
                    "topic": topic,
                    "service_type": service_type,
                    "corpus": "callcenter_rag",
                },
            )
        )
    return exports


def _create_vector_store(exports: list[tuple[Path, dict[str, Any]]]) -> str:
    client = OpenAI(api_key=get_settings().openai_api_key)
    file_specs = []
    for path, attributes in exports:
        with path.open("rb") as handle:
            uploaded = client.files.create(file=handle, purpose="assistants")
        file_specs.append({"file_id": uploaded.id, "attributes": attributes})

    vector_store = client.vector_stores.create(
        name=VECTOR_STORE_NAME,
        description="Atenxion call-center mock RAG corpus for supervisor policy search and latency testing.",
        metadata={"company": "Atenxion", "corpus": "callcenter_rag"},
    )
    client.vector_stores.file_batches.create_and_poll(
        vector_store_id=vector_store.id,
        files=file_specs,
        poll_interval_ms=1500,
    )
    ready = client.vector_stores.retrieve(vector_store.id)
    if ready.status != "completed":
        raise RuntimeError(f"Vector store {ready.id} ended with status {ready.status!r}.")
    return ready.id


async def main() -> None:
    documents = await _seed_and_load_documents()
    exports = _write_grouped_markdown_files(documents)
    vector_store_id = _create_vector_store(exports)
    print(f"Created OpenAI vector store: {vector_store_id}")
    print(f"Seeded MongoDB collection: rag_documents ({len(documents)} records)")
    print("Set these environment variables before running the app:")
    print(f"CALLCENTER_RAG_VECTOR_STORE_ID={vector_store_id}")
    print(f"STRESS_LAB_VECTOR_STORE_ID={vector_store_id}")


if __name__ == "__main__":
    asyncio.run(main())
