"""Smoke tests: key read routes must not return HTTP 500."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _unwrap_detail(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    d = payload.get("detail")
    if isinstance(d, dict):
        return d
    return None


def test_health_and_ready_not_500(client: TestClient, api_prefix: str) -> None:
    for path in (f"{api_prefix}/health", f"{api_prefix}/health/ready"):
        r = client.get(path)
        assert r.status_code < 500, f"{path} -> {r.status_code} {r.text}"


def test_projects_list_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 3, "offset": 0})
    assert r.status_code < 500, r.text
    assert r.status_code == 200
    body = r.json()
    assert "items" in body


def test_project_dashboard_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects in database")
    pid = items[0]["id"]
    r2 = client.get(f"{api_prefix}/projects/{pid}/dashboard")
    assert r2.status_code < 500, r2.text


def test_project_sources_and_batches_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects in database")
    pid = items[0]["id"]

    r2 = client.get(f"{api_prefix}/projects/{pid}/sources", params={"limit": 5})
    assert r2.status_code < 500, r2.text

    r3 = client.get(f"{api_prefix}/projects/{pid}/batches", params={"limit": 5})
    assert r3.status_code < 500, r3.text


def test_batch_detail_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 1})
    assert r.status_code == 200
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects in database")
    pid = items[0]["id"]
    r2 = client.get(f"{api_prefix}/projects/{pid}/batches", params={"limit": 1})
    assert r2.status_code == 200, r2.text
    batches = r2.json().get("items") or []
    if not batches:
        pytest.skip("No batches for first project")
    bid = batches[0]["id"]
    r3 = client.get(f"{api_prefix}/batches/{bid}")
    assert r3.status_code < 500, r3.text


def test_public_report_invalid_token_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/report/public/unknown-token-xxxxxxxxxxxx")
    assert r.status_code < 500, r.text
    assert r.status_code == 404
    detail = _unwrap_detail(r.json())
    assert detail is not None
    assert detail.get("code") == "report_not_found"


def test_batch_export_excel_missing_project_returns_404_not_500(
    client: TestClient, api_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: missing Project must be 404, not AssertionError -> 500."""
    from uuid import uuid4

    from app.api.routes import research_batches as rb
    from app.models.research_batch import ResearchBatch

    fake_batch = ResearchBatch(
        id=uuid4(),
        project_id=uuid4(),
        name="t",
        description=None,
    )

    async def fake_batch_or_404(_session: object, _batch_id: object) -> ResearchBatch:
        return fake_batch

    monkeypatch.setattr(rb, "_batch_or_404", fake_batch_or_404)

    r = client.get(f"{api_prefix}/batches/{fake_batch.id}/export/excel")
    assert r.status_code < 500, r.text
    assert r.status_code == 404
    detail = _unwrap_detail(r.json())
    assert detail is not None
    assert detail.get("code") == "project_not_found"
