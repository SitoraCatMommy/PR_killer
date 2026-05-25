"""Smoke: upload .docx → chunk; optional extract + batch report with OpenAI."""

from __future__ import annotations

import io
import os

from docx import Document
from fastapi.testclient import TestClient


def _docx_bytes(*paragraphs: str) -> bytes:
    buf = io.BytesIO()
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    return buf.getvalue()


def test_docx_upload_chunk_smoke(client: TestClient, api_prefix: str) -> None:
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": "smoke-docx-flow", "output_language": "ru"},
    )
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    r2 = client.post(
        f"{api_prefix}/projects/{project_id}/batches",
        json={"name": "smoke-docx-batch", "description": None},
    )
    assert r2.status_code == 201, r2.text
    batch_id = r2.json()["id"]

    body = _docx_bytes(
        "Смоук-тест DOCX: первая абзац для чанкования.",
        "Вторая абзац с дополнительным текстом для NLP pipeline.",
    )
    files = {
        "file": (
            "smoke.docx",
            body,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r3 = client.post(
        f"{api_prefix}/projects/{project_id}/sources/text/upload",
        files=files,
        data={"source_type": "upload"},
    )
    assert r3.status_code == 201, r3.text
    doc_id = r3.json()["id"]

    add = client.post(
        f"{api_prefix}/batches/{batch_id}/sources",
        json={"source_document_id": str(doc_id)},
    )
    assert add.status_code == 201, add.text

    from app.workers.tasks.research_processing import chunk_source_document

    out = chunk_source_document.run(str(doc_id), "fixed")
    assert out.get("status") == "ok", out

    ch = client.get(f"{api_prefix}/sources/documents/{doc_id}/chunks")
    assert ch.status_code == 200
    assert len(ch.json()) >= 1

    if (os.getenv("OPENAI_API_KEY") or "").strip():
        from app.workers.tasks.research_extraction import extract_entities_for_document
        from app.workers.tasks.research_batch_report import generate_batch_research_report

        extract_entities_for_document.run(str(doc_id))
        rep = generate_batch_research_report.run(str(project_id), str(batch_id), "ru")
        assert rep.get("status") == "ok", rep
