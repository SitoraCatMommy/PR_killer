"""Smoke: transcript export + promote, then chunk (sync) and optional extract with OpenAI."""

from __future__ import annotations

import io
import os
import wave
from uuid import UUID

from fastapi.testclient import TestClient

from app.domain.enums import JobStatus
from app.infrastructure.db_sync import sync_session_scope
from app.models.transcript import Transcript


def _tiny_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 80)
    return buf.getvalue()


def test_export_promote_chunk_smoke(client: TestClient, api_prefix: str) -> None:
    """Seeded completed transcript → export docx/txt → promote → chunk.run (no Celery)."""
    r = client.post(
        f"{api_prefix}/projects",
        json={"name": "smoke-transcript-flow", "output_language": "ru"},
    )
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    r2 = client.post(
        f"{api_prefix}/projects/{project_id}/batches",
        json={"name": "smoke-batch", "description": None},
    )
    assert r2.status_code == 201, r2.text
    batch_id = r2.json()["id"]

    files = {"file": ("smoke.wav", _tiny_wav(), "audio/wav")}
    r3 = client.post(
        f"{api_prefix}/projects/{project_id}/sources/audio/upload",
        files=files,
        data={"source_type": "upload"},
    )
    assert r3.status_code == 201, r3.text
    audio_id = r3.json()["id"]

    with sync_session_scope() as session:
        tr = Transcript(
            source_audio_id=UUID(audio_id),
            full_text="Смоук-тест: перенос транскрипта в документ.\n\nВторая абзац.",
            language="ru",
            status=JobStatus.COMPLETED,
            provider_name="pytest",
        )
        session.add(tr)
        session.commit()

    ex = client.get(f"{api_prefix}/sources/audios/{audio_id}/transcript/export?format=txt")
    assert ex.status_code == 200, ex.text
    cyr_smoke = b"\xd0\xa1\xd0\xbc\xd0\xbe\xd1\x83\xd0\xba"
    assert cyr_smoke in ex.content or b"smoke" in ex.content.lower()

    exd = client.get(f"{api_prefix}/sources/audios/{audio_id}/transcript/export?format=docx")
    assert exd.status_code == 200, exd.text
    assert exd.content[:2] == b"PK"

    body = {
        "target_project_id": project_id,
        "research_batch_id": batch_id,
        "filename_stem": "promoted_smoke",
    }
    pr = client.post(f"{api_prefix}/sources/audios/{audio_id}/transcript/promote", json=body)
    assert pr.status_code == 201, pr.text
    doc_id = pr.json()["source_document_id"]

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
