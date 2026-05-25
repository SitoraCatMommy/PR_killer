"""Drain batch processing queue: fan-out all pending sources to parallel Celery tasks."""

from __future__ import annotations

import logging
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.services.batch_queue_service import (
    maybe_finalize_batch_after_audio_failure,
    maybe_finalize_batch_after_document_pipeline,
    mark_batch_source_processing,
    pick_all_pending_batch_sources_sync,
    release_batch_queue_lock,
    schedule_batch_queue,
    try_acquire_batch_queue_lock,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.batch_processing_queue.process_batch_processing_queue",
    time_limit=6 * 3600,
    soft_time_limit=350 * 60,
)
def process_batch_processing_queue(batch_id: str) -> dict:
    """Mark all pending batch sources processing and enqueue document/audio pipelines (parallel)."""
    bid = UUID(batch_id)
    lock = try_acquire_batch_queue_lock(bid)
    if not lock.acquired:
        if lock.busy:
            schedule_batch_queue(bid, countdown=5)
        return {"status": "skipped_locked", "batch_id": batch_id}
    try:
        rows: list = []
        with sync_session_scope() as session:
            rows = pick_all_pending_batch_sources_sync(session, bid, limit=64)
            for src in rows:
                mark_batch_source_processing(session, src)

        if not rows:
            logger.info("batch_queue: idle batch=%s", batch_id)
            return {"status": "idle", "batch_id": batch_id}

        from app.workers.tasks.audio_segment_pipeline import transcribe_full_audio_gemini_fast
        from app.workers.tasks.research_source_full_pipeline import pipeline_document_analysis

        doc_dispatched = 0
        audio_dispatched = 0
        for src in rows:
            doc_id = src.source_document_id
            audio_id = src.source_audio_id
            if doc_id is not None:
                try:
                    pipeline_document_analysis.delay(str(doc_id))
                    doc_dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("batch_queue: document pipeline enqueue failed batch=%s doc=%s", batch_id, doc_id)
                    maybe_finalize_batch_after_document_pipeline(
                        doc_id,
                        pipeline_ok=False,
                        error_message=repr(exc),
                    )
            elif audio_id is not None:
                try:
                    transcribe_full_audio_gemini_fast.delay(str(audio_id))
                    audio_dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("batch_queue: audio ASR enqueue failed batch=%s audio=%s", batch_id, audio_id)
                    maybe_finalize_batch_after_audio_failure(audio_id, error_message=repr(exc))
            else:
                logger.warning("batch_queue: source row had neither doc nor audio batch=%s row=%s", batch_id, src.id)

        logger.info(
            "batch_queue: fan-out batch=%s sources=%s docs=%s audio=%s",
            batch_id,
            len(rows),
            doc_dispatched,
            audio_dispatched,
        )
        return {
            "status": "fan_out",
            "batch_id": batch_id,
            "sources": len(rows),
            "documents_dispatched": doc_dispatched,
            "audio_dispatched": audio_dispatched,
        }
    finally:
        if lock.token:
            release_batch_queue_lock(bid, lock.token)
