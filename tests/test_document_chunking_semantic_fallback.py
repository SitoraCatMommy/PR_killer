"""Deterministic fallback when OpenAI semantic chunking fails."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.source_document import SourceDocument
from app.services.openai_semantic_chunking_service import OpenAISemanticChunkingService


def _create_project_batch_txt(client: TestClient, api_prefix: str) -> tuple[str, str, str]:
    r = client.post(f"{api_prefix}/projects", json={"name": "fallback-test", "output_language": "ru"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    r2 = client.post(
        f"{api_prefix}/projects/{project_id}/batches",
        json={"name": "fallback-batch", "description": None},
    )
    assert r2.status_code == 201, r2.text
    batch_id = r2.json()["id"]

    long_body = ("Интервью: респондент описывает опыт с продуктом. " * 250)[:12000]
    assert len(long_body) >= 6000
    r3 = client.post(
        f"{api_prefix}/projects/{project_id}/sources/text/upload",
        files={"file": ("long.txt", long_body.encode("utf-8"), "text/plain")},
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


def test_openai_chunking_falls_back_to_fixed_on_semantic_error(
    client: TestClient,
    api_prefix: str,
) -> None:
    if not (get_settings().openai_api_key or "").strip():
        pytest.skip("OPENAI_API_KEY not set")

    _pid, _bid, doc_id = _create_project_batch_txt(client, api_prefix)

    def _boom(_self: OpenAISemanticChunkingService, _text: str) -> list[str]:
        raise TimeoutError("simulated semantic timeout")

    from app.workers.tasks.research_processing import chunk_source_document

    with patch.object(OpenAISemanticChunkingService, "chunk_full_text", _boom):
        out = chunk_source_document.run(doc_id, "openai")

    assert out.get("status") == "ok", out
    assert int(out.get("chunk_count") or 0) > 0

    with sync_session_scope() as session:
        doc = session.get(SourceDocument, UUID(doc_id))
        assert doc is not None
        pipe = doc.pipeline_state_json or {}
        assert pipe.get("phase") == "chunked"
        assert pipe.get("fallback_used") is True


def test_recover_pipeline_queues_failed_document(client: TestClient, api_prefix: str) -> None:
    _pid, batch_id, doc_id = _create_project_batch_txt(client, api_prefix)
    did = UUID(doc_id)
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, did)
        assert doc is not None
        doc.pipeline_state_json = {
            **(doc.pipeline_state_json or {}),
            "phase": "parsed",
            "extraction": {"status": "chunk_failed", "reason": "simulated", "entities_created": 0},
        }
        session.commit()

    r = client.post(f"{api_prefix}/batches/{batch_id}/documents/recover-pipeline")
    assert r.status_code == 202, r.text
    body = r.json()
    assert str(did) in {str(x) for x in body["queued_document_ids"]}
    assert len(body["pipeline_task_ids"]) == len(body["queued_document_ids"])
