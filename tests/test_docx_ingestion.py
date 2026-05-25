"""Tests: Word .docx text upload (raw_text) and stable 422 error codes."""

from __future__ import annotations

import io
from typing import Any

from docx import Document
from fastapi.testclient import TestClient


def _unwrap_detail(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    d = payload.get("detail")
    if isinstance(d, dict):
        return d
    return None


def _docx_bytes(*paragraphs: str) -> bytes:
    buf = io.BytesIO()
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    return buf.getvalue()


def test_upload_valid_docx_populates_raw_text(client: TestClient, api_prefix: str) -> None:
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": "pytest-docx-ingest", "output_language": "ru"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    body = _docx_bytes("Первая строка из DOCX.", "Вторая строка.")
    files = {
        "file": (
            "sample.docx",
            body,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r2 = client.post(
        f"{api_prefix}/projects/{pid}/sources/text/upload",
        files=files,
        data={"source_type": "upload"},
    )
    assert r2.status_code == 201, r2.text
    data = r2.json()
    rt = data.get("raw_text") or ""
    assert len(rt.strip()) > 0
    assert "Первая строка" in rt
    assert data.get("original_path") is None


def test_upload_corrupt_docx_returns_422(client: TestClient, api_prefix: str) -> None:
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": "pytest-docx-corrupt", "output_language": "ru"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    files = {
        "file": (
            "broken.docx",
            b"PK\x03\x04not-a-valid-docx-zip",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r2 = client.post(
        f"{api_prefix}/projects/{pid}/sources/text/upload",
        files=files,
        data={"source_type": "upload"},
    )
    assert r2.status_code == 422, r2.text
    detail = _unwrap_detail(r2.json())
    assert detail is not None
    assert detail.get("code") == "docx_corrupt_or_unreadable"


def test_upload_empty_text_docx_returns_422(client: TestClient, api_prefix: str) -> None:
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": "pytest-docx-empty", "output_language": "ru"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    files = {
        "file": (
            "empty.docx",
            _docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r2 = client.post(
        f"{api_prefix}/projects/{pid}/sources/text/upload",
        files=files,
        data={"source_type": "upload"},
    )
    assert r2.status_code == 422, r2.text
    detail = _unwrap_detail(r2.json())
    assert detail is not None
    assert detail.get("code") == "docx_empty"
