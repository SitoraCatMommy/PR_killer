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


def test_project_analysis_routes_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects in database")
    pid = items[0]["id"]
    for path in (
        f"/projects/{pid}/process",
        f"/projects/{pid}/audience-portrait",
        f"/projects/{pid}/pr-strategy",
        f"/projects/{pid}/full-report",
    ):
        method = "post" if path.endswith("/process") else "get"
        if method == "post":
            resp = client.post(f"{api_prefix}{path}")
        else:
            resp = client.get(f"{api_prefix}{path}")
        assert resp.status_code < 500, f"{path} -> {resp.status_code} {resp.text}"


def test_project_sources_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/projects", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    if not items:
        pytest.skip("No projects in database")
    pid = items[0]["id"]

    r2 = client.get(f"{api_prefix}/projects/{pid}/sources", params={"limit": 5})
    assert r2.status_code < 500, r2.text

def test_public_report_invalid_token_not_500(client: TestClient, api_prefix: str) -> None:
    r = client.get(f"{api_prefix}/report/public/unknown-token-xxxxxxxxxxxx")
    assert r.status_code < 500, r.text
    assert r.status_code == 404
    detail = _unwrap_detail(r.json())
    assert detail is not None
    assert detail.get("code") == "report_not_found"


