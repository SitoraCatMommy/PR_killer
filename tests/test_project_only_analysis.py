"""Project-only analysis: upload, processing queue, public report token resolution."""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _create_project(client: TestClient, api_prefix: str, name: str | None = None) -> str:
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": name or f"proj-{uuid4().hex[:8]}", "description": "test"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_project_bulk_upload_and_process_endpoints(client: TestClient, api_prefix: str) -> None:
    pid = _create_project(client, api_prefix)
    content = b"Interview transcript line one.\nLine two with product feedback.\n"
    files = [("files", ("interview.txt", io.BytesIO(content), "text/plain"))]
    r = client.post(
        f"{api_prefix}/projects/{pid}/sources/bulk-upload",
        data={"metadata_json": "{}", "run_analysis": "false"},
        files=files,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body.get("created") or []) == 1

    r2 = client.post(f"{api_prefix}/projects/{pid}/process")
    assert r2.status_code == 202, r2.text
    assert r2.json().get("status") == "queued"


def test_project_public_link_and_invalid_token(client: TestClient, api_prefix: str) -> None:
    pid = _create_project(client, api_prefix)
    r = client.post(f"{api_prefix}/projects/{pid}/public-link")
    assert r.status_code == 200, r.text
    token = r.json().get("token")
    assert token

    r404 = client.get(f"{api_prefix}/report/public/unknown-token-xxxxxxxxxxxx")
    assert r404.status_code == 404
    detail = r404.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == "report_not_found"


def test_project_dashboard_and_readiness_not_500(client: TestClient, api_prefix: str) -> None:
    pid = _create_project(client, api_prefix)
    r = client.get(f"{api_prefix}/projects/{pid}/dashboard")
    assert r.status_code < 500, r.text
    r2 = client.get(f"{api_prefix}/projects/{pid}/pr-analysis/readiness")
    assert r2.status_code < 500, r2.text


@pytest.mark.skip(reason="Requires OPENAI_API_KEY and processed corpus")
def test_project_full_report_requires_llm(client: TestClient, api_prefix: str) -> None:
    pid = _create_project(client, api_prefix)
    r = client.get(f"{api_prefix}/projects/{pid}/full-report")
    assert r.status_code in (200, 502, 503)
