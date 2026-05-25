"""Document chunking idempotency and row-lock behaviour (no duplicate interview_units)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.db_sync import sync_session_scope
from app.models.source_document import SourceDocument


def _create_txt_doc_in_batch(client: TestClient, api_prefix: str) -> tuple[str, str, str]:
    r = client.post(f"{api_prefix}/projects", json={"name": "race-doc", "output_language": "ru"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    r2 = client.post(
        f"{api_prefix}/projects/{project_id}/batches",
        json={"name": "race-batch", "description": None},
    )
    assert r2.status_code == 201, r2.text
    batch_id = r2.json()["id"]

    body = ("Параллельный тест чанкования. " * 120)[:8000]
    r3 = client.post(
        f"{api_prefix}/projects/{project_id}/sources/text/upload",
        files={"file": ("race.txt", body.encode("utf-8"), "text/plain")},
        data={"source_type": "upload"},
    )
    assert r3.status_code == 201, r3.text
    doc_id = r3.json()["id"]

    add = client.post(
        f"{api_prefix}/batches/{batch_id}/sources",
        json={"source_document_id": str(doc_id)},
    )
    assert add.status_code == 201, add.text
    return project_id, batch_id, doc_id


def test_sequential_second_chunk_is_noop(client: TestClient, api_prefix: str) -> None:
    _pid, _bid, doc_id = _create_txt_doc_in_batch(client, api_prefix)
    from app.workers.tasks.research_processing import chunk_source_document

    r1 = chunk_source_document.run(doc_id, "fixed")
    assert r1.get("status") == "ok", r1
    assert int(r1.get("chunk_count") or 0) > 0

    r2 = chunk_source_document.run(doc_id, "fixed")
    assert r2.get("status") == "ok", r2
    assert r2.get("chunk_status") == "noop_already_chunked"
    assert int(r2.get("chunk_count") or 0) == int(r1.get("chunk_count") or 0)


def test_parallel_chunk_tasks_do_not_integrity_error(client: TestClient, api_prefix: str) -> None:
    _pid, _bid, doc_id = _create_txt_doc_in_batch(client, api_prefix)
    from app.workers.tasks.research_processing import chunk_source_document

    def _one(_: int) -> dict:
        return chunk_source_document.run(doc_id, "fixed")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_one, i) for i in range(6)]
        results = [f.result() for f in as_completed(futures)]

    statuses = {r.get("status") for r in results}
    assert statuses <= {"ok", "already_processing"}, results
    assert any(int(r.get("chunk_count") or 0) > 0 for r in results)


def test_recover_skips_actively_running_document(client: TestClient, api_prefix: str) -> None:
    _pid, batch_id, doc_id = _create_txt_doc_in_batch(client, api_prefix)
    did = UUID(doc_id)
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, did)
        assert doc is not None
        doc.pipeline_state_json = {
            **(doc.pipeline_state_json or {}),
            "phase": "chunking",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "extraction": {"status": "pending", "reason": None, "entities_created": 0},
        }
        session.commit()

    r = client.post(f"{api_prefix}/batches/{batch_id}/documents/recover-pipeline")
    assert r.status_code == 202, r.text
    body = r.json()
    assert str(did) not in {str(x) for x in body["queued_document_ids"]}
    assert str(did) in {str(x) for x in body["skipped_document_ids"]}
