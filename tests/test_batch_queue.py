"""Batch processing queue: summary counts, Redis lock, API surface."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.batch_cached_llm_service import make_cache_key
from app.services.batch_queue_service import (
    compute_batch_queue_summary,
    release_batch_queue_lock,
    try_acquire_batch_queue_lock,
)


def test_compute_batch_queue_summary_counts() -> None:
    pid = uuid4()
    rows = [
        SimpleNamespace(processing_status="idle", id=None),
        SimpleNamespace(processing_status="pending", id=None),
        SimpleNamespace(processing_status="processing", id=pid),
        SimpleNamespace(processing_status="completed", id=None),
        SimpleNamespace(processing_status="failed", id=None),
        SimpleNamespace(processing_status="unknown_state", id=None),
    ]
    s = compute_batch_queue_summary(rows)
    assert s["idle"] == 2
    assert s["pending"] == 1
    assert s["processing"] == 1
    assert s["completed"] == 1
    assert s["failed"] == 1
    assert s["currently_processing_row_id"] == pid


def test_make_cache_key_includes_data_revision() -> None:
    bid = uuid4()
    k1 = make_cache_key("pr_strategy", bid, None, None, "ru", multi_interview_mode=True, data_revision="abc")
    k2 = make_cache_key("pr_strategy", bid, None, None, "ru", multi_interview_mode=True, data_revision="def")
    assert k1 != k2
    k3 = make_cache_key("pr_strategy", bid, None, None, "ru", multi_interview_mode=True, data_revision="abc")
    assert k1 == k3


@pytest.mark.integration
def test_batch_queue_redis_lock_busy_then_release() -> None:
    """Requires Redis at REDIS_URL (same as API health/ready)."""
    bid = uuid4()
    first = try_acquire_batch_queue_lock(bid)
    assert first.acquired
    assert not first.busy
    second = try_acquire_batch_queue_lock(bid)
    assert not second.acquired
    assert second.busy
    if first.token:
        release_batch_queue_lock(bid, first.token)
    third = try_acquire_batch_queue_lock(bid)
    assert third.acquired
    assert third.token
    release_batch_queue_lock(bid, third.token)


@pytest.mark.integration
def test_get_batch_includes_queue_summary(client: TestClient, api_prefix: str) -> None:
    r = client.post(f"{api_prefix}/projects", json={"name": "pytest-batch-queue", "output_language": "ru"})
    if r.status_code != 201:
        pytest.skip(f"cannot create project: {r.status_code}")
    pid = r.json()["id"]
    r2 = client.post(f"{api_prefix}/projects/{pid}/batches", json={"name": "bq1", "description": None})
    assert r2.status_code == 201, r2.text
    bid = r2.json()["id"]
    r3 = client.get(f"{api_prefix}/batches/{bid}")
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert "queue_summary" in body
    qs = body["queue_summary"]
    assert qs["idle"] == 0
    assert qs["pending"] == 0
    assert qs["processing"] == 0
    assert qs["completed"] == 0
    assert qs["failed"] == 0
