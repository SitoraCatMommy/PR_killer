"""Batch processing queue: fan-out pending sources to Celery tasks, finalize rows, advance queue."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis as redis_sync
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import BatchSourceProcessingStatus
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.research_batch_llm_cache import ResearchBatchLlmCache
from app.models.research_batch_source import ResearchBatchSource
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument

logger = logging.getLogger(__name__)

BATCH_ANALYSIS_META_KEY = "_batch_analysis"

BATCH_QUEUE_LOCK_PREFIX = "ria:batch_queue_lock:"
BATCH_QUEUE_LOCK_TTL_SECONDS = 6 * 3600

_sync_redis_client: redis_sync.Redis | None = None


def _get_sync_redis_client() -> redis_sync.Redis:
    global _sync_redis_client
    if _sync_redis_client is None:
        _sync_redis_client = redis_sync.Redis.from_url(
            str(get_settings().redis_url),
            decode_responses=True,
        )
    return _sync_redis_client


@dataclass(frozen=True)
class BatchQueueLockResult:
    """Redis lock for serializing ``process_batch_processing_queue`` per batch_id."""

    acquired: bool
    """True if this worker may drain the queue (or degraded mode without Redis)."""
    token: str
    """Non-empty when a Redis lock was taken; release in ``finally``."""
    busy: bool
    """True when another worker holds the lock (caller should reschedule)."""


def try_acquire_batch_queue_lock(batch_id: UUID) -> BatchQueueLockResult:
    """Try SET NX on Redis. On Redis errors, proceed without lock (degraded)."""
    try:
        r = _get_sync_redis_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_queue_lock: redis client failed batch=%s err=%s", batch_id, exc)
        return BatchQueueLockResult(acquired=True, token="", busy=False)

    key = f"{BATCH_QUEUE_LOCK_PREFIX}{batch_id}"
    token = secrets.token_urlsafe(16)
    try:
        ok = bool(r.set(key, token, nx=True, ex=BATCH_QUEUE_LOCK_TTL_SECONDS))
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_queue_lock: SET failed batch=%s err=%s", batch_id, exc)
        return BatchQueueLockResult(acquired=True, token="", busy=False)

    if ok:
        return BatchQueueLockResult(acquired=True, token=token, busy=False)
    return BatchQueueLockResult(acquired=False, token="", busy=True)


def release_batch_queue_lock(batch_id: UUID, token: str) -> None:
    if not token:
        return
    try:
        r = _get_sync_redis_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_queue_lock: release client failed batch=%s err=%s", batch_id, exc)
        return
    key = f"{BATCH_QUEUE_LOCK_PREFIX}{batch_id}"
    lua = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    try:
        r.eval(lua, 1, key, token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_queue_lock: release EVAL failed batch=%s err=%s", batch_id, exc)


def compute_batch_queue_summary(sources: Iterable[Any]) -> dict[str, Any]:
    idle = pending = processing = completed = failed = 0
    current_row: UUID | None = None
    for row in sources:
        raw = getattr(row, "processing_status", None)
        st = str(raw or "").strip().lower()
        if st == BatchSourceProcessingStatus.IDLE.value:
            idle += 1
        elif st == BatchSourceProcessingStatus.PENDING.value:
            pending += 1
        elif st == BatchSourceProcessingStatus.PROCESSING.value:
            processing += 1
            if current_row is None:
                rid = getattr(row, "id", None)
                current_row = rid if isinstance(rid, UUID) else None
        elif st == BatchSourceProcessingStatus.COMPLETED.value:
            completed += 1
        elif st == BatchSourceProcessingStatus.FAILED.value:
            failed += 1
        else:
            idle += 1
    return {
        "idle": idle,
        "pending": pending,
        "processing": processing,
        "completed": completed,
        "failed": failed,
        "currently_processing_row_id": current_row,
    }


def _batch_analysis_from_doc(doc: SourceDocument | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    meta = doc.metadata_json or {}
    ba = meta.get(BATCH_ANALYSIS_META_KEY)
    return ba if isinstance(ba, dict) else None


def _batch_analysis_from_audio_dict(metadata_json: dict[str, Any] | None) -> dict[str, Any] | None:
    meta = metadata_json or {}
    ba = meta.get(BATCH_ANALYSIS_META_KEY)
    return ba if isinstance(ba, dict) else None


def invalidate_batch_llm_cache_sync(session: Session, batch_id: UUID) -> None:
    session.execute(delete(ResearchBatchLlmCache).where(ResearchBatchLlmCache.batch_id == batch_id))
    session.flush()


def schedule_batch_queue(batch_id: UUID, *, countdown: int | None = None) -> None:
    """Enqueue the next queue drain (lazy import avoids Celery circular imports)."""
    from app.workers.tasks.batch_processing_queue import process_batch_processing_queue

    if countdown and countdown > 0:
        process_batch_processing_queue.apply_async(args=[str(batch_id)], countdown=countdown)
    else:
        process_batch_processing_queue.delay(str(batch_id))


def _resolve_document_batch_row(
    session: Session, source_document_id: UUID
) -> tuple[ResearchBatchSource, UUID] | None:
    """Resolve batch queue row from ``_batch_analysis`` metadata or PROCESSING FK fallback."""
    doc = session.get(SourceDocument, source_document_id)
    if doc is None:
        return None
    ba = _batch_analysis_from_doc(doc)
    if ba:
        row_id_raw = ba.get("batch_source_row_id")
        batch_id_raw = ba.get("batch_id")
        if row_id_raw and batch_id_raw:
            try:
                row_id = UUID(str(row_id_raw))
                batch_id = UUID(str(batch_id_raw))
            except ValueError:
                logger.warning("batch_queue: invalid UUID in doc metadata doc=%s", source_document_id)
            else:
                row = session.get(ResearchBatchSource, row_id)
                if row is not None and row.batch_id == batch_id:
                    return (row, batch_id)
    row = session.scalar(
        select(ResearchBatchSource)
        .where(
            ResearchBatchSource.source_document_id == source_document_id,
            ResearchBatchSource.processing_status == BatchSourceProcessingStatus.PROCESSING.value,
        )
        .order_by(ResearchBatchSource.created_at.desc())
        .limit(1)
    )
    if row is not None:
        return (row, row.batch_id)
    return None


def _resolve_audio_batch_row(
    session: Session, source_audio_id: UUID, *, metadata_json: dict[str, Any] | None
) -> tuple[ResearchBatchSource, UUID] | None:
    ba = _batch_analysis_from_audio_dict(metadata_json)
    if ba:
        row_id_raw = ba.get("batch_source_row_id")
        batch_id_raw = ba.get("batch_id")
        if row_id_raw and batch_id_raw:
            try:
                row_id = UUID(str(row_id_raw))
                batch_id = UUID(str(batch_id_raw))
            except ValueError:
                logger.warning("batch_queue: invalid UUID in audio metadata audio=%s", source_audio_id)
            else:
                row = session.get(ResearchBatchSource, row_id)
                if row is not None and row.batch_id == batch_id:
                    return (row, batch_id)
    row = session.scalar(
        select(ResearchBatchSource)
        .where(
            ResearchBatchSource.source_audio_id == source_audio_id,
            ResearchBatchSource.processing_status == BatchSourceProcessingStatus.PROCESSING.value,
        )
        .order_by(ResearchBatchSource.created_at.desc())
        .limit(1)
    )
    if row is not None:
        return (row, row.batch_id)
    return None


def maybe_finalize_batch_after_document_pipeline(
    source_document_id: UUID,
    *,
    pipeline_ok: bool,
    error_message: str | None = None,
) -> None:
    """Mark batch source completed/failed and advance queue when document is tied to a batch row."""
    batch_id: UUID | None = None
    with sync_session_scope() as session:
        resolved = _resolve_document_batch_row(session, source_document_id)
        if resolved is None:
            return
        row, bid = resolved
        batch_id = bid
        now = datetime.now(timezone.utc)
        if pipeline_ok:
            row.processing_status = BatchSourceProcessingStatus.COMPLETED.value
            row.completed_at = now
            row.last_error = None
        else:
            row.processing_status = BatchSourceProcessingStatus.FAILED.value
            row.last_error = (error_message or "pipeline_failed")[:8000]
            row.completed_at = now
        session.flush()
        invalidate_batch_llm_cache_sync(session, bid)

    if batch_id is not None:
        schedule_batch_queue(batch_id)


def maybe_finalize_batch_after_audio_extract_outcome(
    transcript_id: UUID,
    *,
    pipeline_ok: bool,
    error_message: str | None = None,
) -> None:
    """Finalize queued batch audio source after transcript extraction (success or failure)."""
    from app.models.transcript import Transcript

    batch_id: UUID | None = None
    with sync_session_scope() as session:
        tr = session.get(Transcript, transcript_id)
        if tr is None or tr.source_audio_id is None:
            return
        audio = session.get(SourceAudio, tr.source_audio_id)
        if audio is None:
            return
        resolved = _resolve_audio_batch_row(session, audio.id, metadata_json=audio.metadata_json)
        if resolved is None:
            return
        row, bid = resolved
        batch_id = bid
        now = datetime.now(timezone.utc)
        if pipeline_ok:
            row.processing_status = BatchSourceProcessingStatus.COMPLETED.value
            row.completed_at = now
            row.last_error = None
        else:
            row.processing_status = BatchSourceProcessingStatus.FAILED.value
            row.last_error = (error_message or "transcript_extraction_failed")[:8000]
            row.completed_at = now
        session.flush()
        invalidate_batch_llm_cache_sync(session, bid)

    if batch_id is not None:
        schedule_batch_queue(batch_id)


def maybe_finalize_batch_after_audio_extract(transcript_id: UUID) -> None:
    """After transcript entity extraction completes successfully, finalize queued batch audio source."""
    maybe_finalize_batch_after_audio_extract_outcome(transcript_id, pipeline_ok=True)


def maybe_finalize_batch_after_audio_failure(source_audio_id: UUID, *, error_message: str) -> None:
    """When chunked ASR merge fails entirely, mark batch source failed and advance."""
    batch_id: UUID | None = None
    with sync_session_scope() as session:
        audio = session.get(SourceAudio, source_audio_id)
        if audio is None:
            return
        resolved = _resolve_audio_batch_row(session, source_audio_id, metadata_json=audio.metadata_json)
        if resolved is None:
            return
        row, bid = resolved
        batch_id = bid
        now = datetime.now(timezone.utc)
        row.processing_status = BatchSourceProcessingStatus.FAILED.value
        row.last_error = (error_message or "audio_pipeline_failed")[:8000]
        row.completed_at = now
        session.flush()
        invalidate_batch_llm_cache_sync(session, bid)

    if batch_id is not None:
        schedule_batch_queue(batch_id)


def requeue_batch_document_pipeline(source_document_id: UUID, *, reason: str, countdown: int = 30) -> None:
    """Put a temporarily busy document back into the batch queue instead of stalling the batch."""
    batch_id: UUID | None = None
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, source_document_id)
        ba = _batch_analysis_from_doc(doc)
        if not ba:
            return
        row_id_raw = ba.get("batch_source_row_id")
        batch_id_raw = ba.get("batch_id")
        if not row_id_raw or not batch_id_raw:
            return
        try:
            row_id = UUID(str(row_id_raw))
            batch_id = UUID(str(batch_id_raw))
        except ValueError:
            logger.warning("batch_queue: invalid UUID in doc metadata doc=%s", source_document_id)
            return
        row = session.get(ResearchBatchSource, row_id)
        if row is None or row.batch_id != batch_id:
            return
        row.processing_status = BatchSourceProcessingStatus.PENDING.value
        row.last_error = (reason or "document_pipeline_busy")[:8000]
        row.started_at = None
        session.flush()

    if batch_id is not None:
        schedule_batch_queue(batch_id, countdown=countdown)


def pick_next_pending_batch_source_sync(session: Session, batch_id: UUID) -> ResearchBatchSource | None:
    stmt = (
        select(ResearchBatchSource)
        .where(
            ResearchBatchSource.batch_id == batch_id,
            ResearchBatchSource.processing_status == BatchSourceProcessingStatus.PENDING.value,
        )
        .order_by(ResearchBatchSource.sort_order.asc(), ResearchBatchSource.created_at.asc())
        .limit(1)
    )
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    else:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def pick_all_pending_batch_sources_sync(
    session: Session, batch_id: UUID, *, limit: int = 64
) -> list[ResearchBatchSource]:
    """Lock and return up to ``limit`` pending sources for parallel fan-out."""
    stmt = (
        select(ResearchBatchSource)
        .where(
            ResearchBatchSource.batch_id == batch_id,
            ResearchBatchSource.processing_status == BatchSourceProcessingStatus.PENDING.value,
        )
        .order_by(ResearchBatchSource.sort_order.asc(), ResearchBatchSource.created_at.asc())
        .limit(limit)
    )
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    else:
        stmt = stmt.with_for_update()
    return list(session.scalars(stmt).all())


def mark_batch_source_processing(session: Session, row: ResearchBatchSource) -> None:
    row.processing_status = BatchSourceProcessingStatus.PROCESSING.value
    row.started_at = datetime.now(timezone.utc)
    session.flush()


def merge_batch_analysis_metadata(
    metadata: dict[str, Any],
    *,
    batch_id: UUID,
    batch_source_row_id: UUID,
    single_file_multi_interview_mode: bool,
) -> dict[str, Any]:
    out = dict(metadata or {})
    out[BATCH_ANALYSIS_META_KEY] = {
        "batch_id": str(batch_id),
        "batch_source_row_id": str(batch_source_row_id),
        "single_file_multi_interview_mode": bool(single_file_multi_interview_mode),
    }
    return out


def finalize_document_pipeline_task_result(source_document_id: UUID, result: dict[str, Any]) -> None:
    """Map pipeline_document_analysis return payload to queue finalization."""
    from app.services.project_queue_service import finalize_project_document_pipeline_task_result

    finalize_project_document_pipeline_task_result(source_document_id, result)

    st = result.get("status")
    if st == "missing":
        maybe_finalize_batch_after_document_pipeline(
            source_document_id,
            pipeline_ok=False,
            error_message="source_document_missing",
        )
        return
    if st == "already_processing":
        requeue_batch_document_pipeline(
            source_document_id,
            reason="document pipeline is already running; queued retry",
        )
        return
    ok = st == "ok"
    err = result.get("error")
    maybe_finalize_batch_after_document_pipeline(
        source_document_id,
        pipeline_ok=ok,
        error_message=str(err) if err is not None else None,
    )
