"""Project processing queue: summary counts, lock, pick ordering."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import SourceProcessingStatus
from app.services.project_queue_service import (
    compute_project_queue_summary,
    project_queue_has_active_work,
    try_acquire_project_queue_lock,
)
from app.services.batch_cached_llm_service import make_cache_key as batch_make_cache_key


def test_compute_project_queue_summary_counts() -> None:
    rows = [
        SimpleNamespace(processing_status="idle", id=None),
        SimpleNamespace(processing_status="pending", id=None),
        SimpleNamespace(processing_status="processing", id=uuid4()),
        SimpleNamespace(processing_status="completed", id=None),
        SimpleNamespace(processing_status="failed", id=None),
    ]
    s = compute_project_queue_summary(rows)
    assert s["idle"] == 1
    assert s["pending"] == 1
    assert s["processing"] == 1
    assert s["completed"] == 1
    assert s["failed"] == 1


def test_project_queue_has_active_work() -> None:
    assert project_queue_has_active_work({"pending": 1, "processing": 0})
    assert project_queue_has_active_work({"pending": 0, "processing": 1})
    assert not project_queue_has_active_work({"pending": 0, "processing": 0, "completed": 3})


def test_make_project_cache_key_includes_data_revision() -> None:
    pid = uuid4()
    k1 = batch_make_cache_key("pr_strategy", pid, None, None, "ru", multi_interview_mode=True, data_revision="abc")
    k2 = batch_make_cache_key("pr_strategy", pid, None, None, "ru", multi_interview_mode=True, data_revision="def")
    assert k1 != k2


@pytest.mark.integration
def test_project_queue_redis_lock_busy_then_release() -> None:
    pid = uuid4()
    first = try_acquire_project_queue_lock(pid)
    assert first.acquired
    assert not first.busy
    second = try_acquire_project_queue_lock(pid)
    assert not second.acquired
    assert second.busy
    from app.services.project_queue_service import release_project_queue_lock

    if first.token:
        release_project_queue_lock(pid, first.token)
    third = try_acquire_project_queue_lock(pid)
    assert third.acquired
    if third.token:
        release_project_queue_lock(pid, third.token)


@pytest.mark.integration
def test_get_project_processing_queue_endpoint(client: TestClient, api_prefix: str) -> None:
    r = client.post(f"{api_prefix}/projects", json={"name": "pytest-project-queue", "output_language": "ru"})
    if r.status_code != 201:
        pytest.skip(f"cannot create project: {r.status_code}")
    pid = r.json()["id"]
    r2 = client.get(f"{api_prefix}/projects/{pid}/processing-queue")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "pending" in body
    assert "processing" in body
    assert "sources" in body


def test_full_report_409_while_processing(client: TestClient, api_prefix: str) -> None:
    r = client.post(f"{api_prefix}/projects", json={"name": "pytest-gate-queue", "output_language": "ru"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    from app.infrastructure.db_sync import sync_session_scope
    from app.domain.enums import SourceType
    from app.models.source_document import SourceDocument

    with sync_session_scope() as session:
        doc = SourceDocument(
            project_id=pid,
            filename="pending.txt",
            source_type=SourceType.UPLOAD,
            raw_text="line one",
            processing_status=SourceProcessingStatus.PENDING.value,
        )
        session.add(doc)
        session.commit()

    r2 = client.get(f"{api_prefix}/projects/{pid}/full-report")
    assert r2.status_code == 409, r2.text
    detail = r2.json().get("detail") or {}
    assert detail.get("code") == "processing_not_complete"
