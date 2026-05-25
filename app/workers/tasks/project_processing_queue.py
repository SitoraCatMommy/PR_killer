"""Drain project processing queue: limited parallel dispatch of pending sources."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.services.project_queue_service import (
    PendingProjectSource,
    mark_project_source_processing,
    pick_pending_project_sources_sync,
    release_project_queue_lock,
    schedule_project_processing,
    try_acquire_project_queue_lock,
)

logger = logging.getLogger(__name__)


def _legacy_fan_out_all(project_id: str, pid: UUID) -> dict:
    doc_ids: list[UUID] = []
    audio_ids: list[UUID] = []
    with sync_session_scope() as session:
        doc_ids = list(
            session.scalars(select(SourceDocument.id).where(SourceDocument.project_id == pid)).all()
        )
        audio_ids = list(
            session.scalars(select(SourceAudio.id).where(SourceAudio.project_id == pid)).all()
        )

    if not doc_ids and not audio_ids:
        logger.info("project_queue: idle project=%s (legacy)", project_id)
        return {"status": "idle", "project_id": project_id}

    from app.workers.tasks.audio_segment_pipeline import transcribe_full_audio_gemini_fast
    from app.workers.tasks.research_source_full_pipeline import pipeline_document_analysis

    doc_dispatched = audio_dispatched = 0
    for did in doc_ids:
        try:
            pipeline_document_analysis.delay(str(did))
            doc_dispatched += 1
        except Exception:  # noqa: BLE001
            logger.exception("project_queue: document enqueue failed project=%s doc=%s", project_id, did)
    for aid in audio_ids:
        try:
            transcribe_full_audio_gemini_fast.delay(str(aid))
            audio_dispatched += 1
        except Exception:  # noqa: BLE001
            logger.exception("project_queue: audio enqueue failed project=%s audio=%s", project_id, aid)

    return {
        "status": "fan_out",
        "project_id": project_id,
        "documents": len(doc_ids),
        "audio": len(audio_ids),
        "documents_dispatched": doc_dispatched,
        "audio_dispatched": audio_dispatched,
    }


@celery_app.task(
    name="app.workers.tasks.project_processing_queue.process_project_processing_queue",
    time_limit=6 * 3600,
    soft_time_limit=350 * 60,
)
def process_project_processing_queue(project_id: str) -> dict:
    """Pick up to N pending sources and enqueue pipelines; reschedule when more work remains."""
    settings = get_settings()
    pid = UUID(project_id)

    if not settings.project_queue_enabled:
        return _legacy_fan_out_all(project_id, pid)

    lock = try_acquire_project_queue_lock(pid)
    if not lock.acquired:
        if lock.busy:
            schedule_project_processing(pid, countdown=5)
        return {"status": "skipped_locked", "project_id": project_id}

    pending: list[PendingProjectSource] = []
    try:
        with sync_session_scope() as session:
            limit = settings.project_queue_concurrency
            pending = pick_pending_project_sources_sync(session, pid, limit=limit)
            for item in pending:
                mark_project_source_processing(session, item)

        if not pending:
            logger.info("project_queue: idle project=%s", project_id)
            return {"status": "idle", "project_id": project_id}

        from app.workers.tasks.audio_segment_pipeline import transcribe_full_audio_gemini_fast
        from app.workers.tasks.research_source_full_pipeline import pipeline_document_analysis

        doc_dispatched = audio_dispatched = 0
        for item in pending:
            if item.kind == "document":
                try:
                    pipeline_document_analysis.delay(str(item.source_id))
                    doc_dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "project_queue: document enqueue failed project=%s doc=%s",
                        project_id,
                        item.source_id,
                    )
                    from app.services.project_queue_service import maybe_finalize_project_after_document_pipeline

                    maybe_finalize_project_after_document_pipeline(
                        item.source_id,
                        pipeline_ok=False,
                        error_message=repr(exc),
                    )
            else:
                try:
                    transcribe_full_audio_gemini_fast.delay(str(item.source_id))
                    audio_dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "project_queue: audio enqueue failed project=%s audio=%s",
                        project_id,
                        item.source_id,
                    )
                    from app.services.project_queue_service import maybe_finalize_project_after_audio_failure

                    maybe_finalize_project_after_audio_failure(item.source_id, error_message=repr(exc))

        logger.info(
            "project_queue: dispatched project=%s pending=%s docs=%s audio=%s",
            project_id,
            len(pending),
            doc_dispatched,
            audio_dispatched,
        )
        return {
            "status": "dispatched",
            "project_id": project_id,
            "picked": len(pending),
            "documents_dispatched": doc_dispatched,
            "audio_dispatched": audio_dispatched,
        }
    finally:
        release_project_queue_lock(pid, lock.token)
