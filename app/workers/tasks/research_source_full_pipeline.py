"""Run chunking + extraction after bulk upload (Celery task; finalizes batch queue rows when applicable)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.services.batch_queue_service import finalize_document_pipeline_task_result
from app.services.interview_units_sync import sync_interview_units_for_document_sync
from app.services.research_document_pipeline_sync import record_extraction_outcome, record_pipeline_failure
from app.workers.tasks.research_extraction import extract_entities_for_document

logger = logging.getLogger(__name__)


def _peek_document_pipeline_state(source_document_id: UUID) -> dict[str, Any]:
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            return {"missing": True}
        n_ch = int(
            session.scalar(
                select(func.count()).select_from(TextChunk).where(TextChunk.source_document_id == source_document_id)
            )
            or 0
        )
        pipe = doc.pipeline_state_json or {}
        phase = str(pipe.get("phase") or "").strip().lower()
        ext = pipe.get("extraction") if isinstance(pipe.get("extraction"), dict) else {}
        ext_status = str(ext.get("status") or "").strip().lower()
        entities_created = int(ext.get("entities_created") or 0)
        return {
            "missing": False,
            "phase": phase,
            "n_chunks": n_ch,
            "extraction_status": ext_status,
            "entities_created": entities_created,
        }


@celery_app.task(name="app.workers.tasks.research_source_full_pipeline.pipeline_document_analysis")
def pipeline_document_analysis(source_document_id: str) -> dict:
    from app.workers.tasks.research_processing import chunk_source_document

    did = UUID(source_document_id)

    def done(payload: dict[str, Any]) -> dict[str, Any]:
        finalize_document_pipeline_task_result(did, payload)
        return payload

    info = _peek_document_pipeline_state(did)
    if info.get("missing"):
        return done({"status": "missing", "source_document_id": source_document_id})

    phase = str(info.get("phase") or "")
    n_ch = int(info.get("n_chunks") or 0)
    ext_status = str(info.get("extraction_status") or "")
    entities_created = int(info.get("entities_created") or 0)

    if phase == "extracted" and ext_status == "ok" and entities_created > 0:
        logger.info("pipeline_document_analysis: skip already complete doc=%s", source_document_id)
        sync_interview_units_for_document_sync(did)
        return done(
            {
                "status": "ok",
                "skipped": "already_complete",
                "source_document_id": source_document_id,
                "chunk": {"chunk_count": n_ch, "skipped_chunk": True},
                "extract": {"status": "skipped", "entities_created": entities_created},
            }
        )

    skip_chunk = (
        n_ch > 0
        and phase in ("chunked", "extracted")
        and ext_status not in ("chunk_failed", "extraction_failed")
    )

    if skip_chunk:
        r1: dict[str, Any] = {
            "status": "ok",
            "chunk_count": n_ch,
            "chunk_status": "noop_already_chunked",
            "skipped_chunk": True,
            "source_document_id": source_document_id,
        }
        logger.info(
            "pipeline_document_analysis: skip chunk (already chunked) doc=%s chunks=%s",
            source_document_id,
            n_ch,
        )
    else:
        try:
            r1 = chunk_source_document.run(source_document_id, "auto")
        except Exception as exc:  # noqa: BLE001
            logger.exception("pipeline_document_analysis: chunk failed doc=%s", source_document_id)
            record_pipeline_failure(did, step="chunk_failed", message=repr(exc))
            return done(
                {
                    "status": "chunk_failed",
                    "source_document_id": source_document_id,
                    "error": repr(exc),
                }
            )

    if r1.get("chunk_status") == "already_processing" or r1.get("status") == "already_processing":
        logger.info("pipeline_document_analysis: chunk busy doc=%s", source_document_id)
        return done(
            {
                "status": "already_processing",
                "source_document_id": source_document_id,
                "chunk": r1,
            }
        )

    cc = int((r1 or {}).get("chunk_count") or 0)
    if cc < 1:
        sync_interview_units_for_document_sync(did)
        record_extraction_outcome(
            did,
            status="skipped_no_chunks",
            reason="chunking_produced_zero_chunks",
            entities_created=0,
            chunk_count_hint=0,
        )
        return done(
            {
                "status": "ok",
                "source_document_id": source_document_id,
                "chunk": r1,
                "extract": {"status": "skipped_no_chunks", "entities_created": 0},
            }
        )

    sync_interview_units_for_document_sync(did)
    try:
        r2 = extract_entities_for_document.run(source_document_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline_document_analysis: extract failed doc=%s", source_document_id)
        record_pipeline_failure(did, step="extraction_failed", message=repr(exc))
        return done(
            {
                "status": "extraction_failed",
                "source_document_id": source_document_id,
                "chunk": r1,
                "error": repr(exc),
            }
        )

    logger.info(
        "pipeline_document_analysis: doc=%s chunk=%s extract=%s",
        source_document_id,
        r1,
        r2,
    )
    return done({"status": "ok", "source_document_id": source_document_id, "chunk": r1, "extract": r2})


@celery_app.task(name="app.workers.tasks.research_source_full_pipeline.pipeline_audio_analysis")
def pipeline_audio_analysis(source_audio_id: str) -> dict:
    """Queue Gemini fast-path or segmented ASR; extraction runs after merge (see ``audio_segment_pipeline``)."""
    from app.workers.tasks.audio_segment_pipeline import transcribe_full_audio_gemini_fast

    r1 = transcribe_full_audio_gemini_fast.delay(source_audio_id)
    logger.info(
        "pipeline_audio_analysis: queued transcription audio=%s task_id=%s",
        source_audio_id,
        r1.id,
    )
    return {"status": "ok", "source_audio_id": source_audio_id, "task_id": str(r1.id)}
