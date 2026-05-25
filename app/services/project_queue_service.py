"""Project-wide source processing queue: drain pending sources with limited concurrency."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import redis as redis_sync
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.domain.enums import SourceProcessingStatus
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.project_llm_cache import ProjectLlmCache
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument

logger = logging.getLogger(__name__)

PROJECT_QUEUE_LOCK_PREFIX = "ria:project_queue_lock:"
PROJECT_QUEUE_LOCK_TTL_SECONDS = 6 * 3600

_sync_redis_client: redis_sync.Redis | None = None


@dataclass(frozen=True)
class PendingProjectSource:
    kind: Literal["document", "audio"]
    source_id: UUID
    sort_order: int
    created_at: datetime


@dataclass(frozen=True)
class ProjectQueueLockResult:
    acquired: bool
    token: str
    busy: bool


def _get_sync_redis_client() -> redis_sync.Redis:
    global _sync_redis_client
    if _sync_redis_client is None:
        _sync_redis_client = redis_sync.Redis.from_url(
            str(get_settings().redis_url),
            decode_responses=True,
        )
    return _sync_redis_client


def try_acquire_project_queue_lock(project_id: UUID) -> ProjectQueueLockResult:
    try:
        r = _get_sync_redis_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("project_queue_lock: redis client failed project=%s err=%s", project_id, exc)
        return ProjectQueueLockResult(acquired=True, token="", busy=False)

    key = f"{PROJECT_QUEUE_LOCK_PREFIX}{project_id}"
    token = secrets.token_urlsafe(16)
    try:
        ok = bool(r.set(key, token, nx=True, ex=PROJECT_QUEUE_LOCK_TTL_SECONDS))
    except Exception as exc:  # noqa: BLE001
        logger.warning("project_queue_lock: SET failed project=%s err=%s", project_id, exc)
        return ProjectQueueLockResult(acquired=True, token="", busy=False)

    if ok:
        return ProjectQueueLockResult(acquired=True, token=token, busy=False)
    return ProjectQueueLockResult(acquired=False, token="", busy=True)


def release_project_queue_lock(project_id: UUID, token: str) -> None:
    if not token:
        return
    try:
        r = _get_sync_redis_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("project_queue_lock: release client failed project=%s err=%s", project_id, exc)
        return
    key = f"{PROJECT_QUEUE_LOCK_PREFIX}{project_id}"
    lua = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    try:
        r.eval(lua, 1, key, token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("project_queue_lock: release EVAL failed project=%s err=%s", project_id, exc)


def compute_project_queue_summary_from_counts(
    *,
    idle: int,
    pending: int,
    processing: int,
    completed: int,
    failed: int,
    currently_processing: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "idle": idle,
        "pending": pending,
        "processing": processing,
        "completed": completed,
        "failed": failed,
        "currently_processing": currently_processing,
    }


def compute_project_queue_summary(rows: Iterable[Any]) -> dict[str, Any]:
    """Summarize mixed document/audio rows that expose ``processing_status``."""
    idle = pending = processing = completed = failed = 0
    currently_processing: list[dict[str, str]] = []
    for row in rows:
        raw = getattr(row, "processing_status", None)
        st = str(raw or "").strip().lower()
        rid = getattr(row, "id", None)
        if st == SourceProcessingStatus.IDLE.value:
            idle += 1
        elif st == SourceProcessingStatus.PENDING.value:
            pending += 1
        elif st == SourceProcessingStatus.PROCESSING.value:
            processing += 1
            if isinstance(rid, UUID):
                kind = "document" if isinstance(row, SourceDocument) else "audio"
                currently_processing.append({"kind": kind, "id": str(rid)})
        elif st == SourceProcessingStatus.COMPLETED.value:
            completed += 1
        elif st == SourceProcessingStatus.FAILED.value:
            failed += 1
        else:
            idle += 1
    return compute_project_queue_summary_from_counts(
        idle=idle,
        pending=pending,
        processing=processing,
        completed=completed,
        failed=failed,
        currently_processing=currently_processing,
    )


def fetch_project_queue_summary_sync(session: Session, project_id: UUID) -> dict[str, Any]:
    docs = list(
        session.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id)).all()
    )
    audios = list(session.scalars(select(SourceAudio).where(SourceAudio.project_id == project_id)).all())
    return compute_project_queue_summary([*docs, *audios])


def project_queue_has_active_work(summary: dict[str, Any]) -> bool:
    return int(summary.get("pending") or 0) > 0 or int(summary.get("processing") or 0) > 0


async def fetch_project_queue_summary_async(session: AsyncSession, project_id: UUID) -> dict[str, Any]:
    docs = list(
        (await session.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id))).all()
    )
    audios = list(
        (await session.scalars(select(SourceAudio).where(SourceAudio.project_id == project_id))).all()
    )
    return compute_project_queue_summary([*docs, *audios])


def invalidate_project_llm_cache_sync(session: Session, project_id: UUID) -> None:
    session.execute(delete(ProjectLlmCache).where(ProjectLlmCache.project_id == project_id))
    session.flush()


def schedule_project_processing(project_id: UUID, *, countdown: int | None = None) -> None:
    from app.workers.tasks.project_processing_queue import process_project_processing_queue

    if countdown and countdown > 0:
        process_project_processing_queue.apply_async(args=[str(project_id)], countdown=countdown)
    else:
        process_project_processing_queue.delay(str(project_id))


async def mark_idle_and_failed_sources_pending_async(session: AsyncSession, project_id: UUID) -> int:
    """Mark idle/failed sources as pending for a full project re-process run."""
    from sqlalchemy import update

    n = 0
    for model in (SourceDocument, SourceAudio):
        res = await session.execute(
            update(model)
            .where(
                model.project_id == project_id,
                model.processing_status.in_(
                    [
                        SourceProcessingStatus.IDLE.value,
                        SourceProcessingStatus.FAILED.value,
                    ]
                ),
            )
            .values(
                processing_status=SourceProcessingStatus.PENDING.value,
                processing_started_at=None,
                processing_completed_at=None,
            )
        )
        n += int(res.rowcount or 0)
    await session.flush()
    return n


async def mark_sources_pending_async(
    session: AsyncSession,
    *,
    document_ids: list[UUID],
    audio_ids: list[UUID],
    sort_base: int = 0,
) -> None:
    ord_i = sort_base
    for did in document_ids:
        doc = await session.get(SourceDocument, did)
        if doc is None:
            continue
        doc.processing_status = SourceProcessingStatus.PENDING.value
        doc.processing_sort_order = ord_i
        doc.processing_started_at = None
        doc.processing_completed_at = None
        doc.processing_last_error = None
        ord_i += 1
    for aid in audio_ids:
        audio = await session.get(SourceAudio, aid)
        if audio is None:
            continue
        audio.processing_status = SourceProcessingStatus.PENDING.value
        audio.processing_sort_order = ord_i
        audio.processing_started_at = None
        audio.processing_completed_at = None
        audio.processing_last_error = None
        ord_i += 1
    await session.flush()


def _next_sort_order_sync(session: Session, project_id: UUID) -> int:
    doc_max = session.scalar(
        select(func.max(SourceDocument.processing_sort_order)).where(SourceDocument.project_id == project_id)
    )
    audio_max = session.scalar(
        select(func.max(SourceAudio.processing_sort_order)).where(SourceAudio.project_id == project_id)
    )
    return max(int(doc_max or 0), int(audio_max or 0), -1) + 1


def mark_source_pending_sync(
    session: Session,
    *,
    kind: Literal["document", "audio"],
    source_id: UUID,
    sort_order: int | None = None,
) -> None:
    if kind == "document":
        row = session.get(SourceDocument, source_id)
    else:
        row = session.get(SourceAudio, source_id)
    if row is None:
        return
    if sort_order is None:
        sort_order = _next_sort_order_sync(session, row.project_id)
    row.processing_status = SourceProcessingStatus.PENDING.value
    row.processing_sort_order = sort_order
    row.processing_started_at = None
    row.processing_completed_at = None
    row.processing_last_error = None
    session.flush()


def pick_pending_project_sources_sync(
    session: Session, project_id: UUID, *, limit: int
) -> list[PendingProjectSource]:
    pending: list[PendingProjectSource] = []
    doc_stmt = (
        select(SourceDocument)
        .where(
            SourceDocument.project_id == project_id,
            SourceDocument.processing_status == SourceProcessingStatus.PENDING.value,
        )
        .order_by(SourceDocument.processing_sort_order.asc(), SourceDocument.created_at.asc())
        .limit(max(limit * 2, limit))
    )
    audio_stmt = (
        select(SourceAudio)
        .where(
            SourceAudio.project_id == project_id,
            SourceAudio.processing_status == SourceProcessingStatus.PENDING.value,
        )
        .order_by(SourceAudio.processing_sort_order.asc(), SourceAudio.created_at.asc())
        .limit(max(limit * 2, limit))
    )
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        doc_stmt = doc_stmt.with_for_update(skip_locked=True)
        audio_stmt = audio_stmt.with_for_update(skip_locked=True)
    else:
        doc_stmt = doc_stmt.with_for_update()
        audio_stmt = audio_stmt.with_for_update()

    for doc in session.scalars(doc_stmt).all():
        pending.append(
            PendingProjectSource(
                kind="document",
                source_id=doc.id,
                sort_order=doc.processing_sort_order,
                created_at=doc.created_at,
            )
        )
    for audio in session.scalars(audio_stmt).all():
        pending.append(
            PendingProjectSource(
                kind="audio",
                source_id=audio.id,
                sort_order=audio.processing_sort_order,
                created_at=audio.created_at,
            )
        )
    pending.sort(key=lambda p: (p.sort_order, p.created_at))
    return pending[:limit]


def mark_project_source_processing(session: Session, item: PendingProjectSource) -> None:
    now = datetime.now(timezone.utc)
    if item.kind == "document":
        row = session.get(SourceDocument, item.source_id)
    else:
        row = session.get(SourceAudio, item.source_id)
    if row is None:
        return
    row.processing_status = SourceProcessingStatus.PROCESSING.value
    row.processing_started_at = now
    session.flush()


def _aggregate_project_after_source(project_id: UUID) -> None:
    try:
        from app.services.research_project_aggregation_service import ResearchProjectAggregationService

        with sync_session_scope() as session:
            ResearchProjectAggregationService().aggregate_project_sync(session, project_id)
    except Exception:  # noqa: BLE001
        logger.exception("project_queue: aggregate failed project=%s", project_id)


def _maybe_finalize_project_queue_idle(project_id: UUID) -> None:
    with sync_session_scope() as session:
        summary = fetch_project_queue_summary_sync(session, project_id)
        if project_queue_has_active_work(summary):
            return
        invalidate_project_llm_cache_sync(session, project_id)
        session.commit()
    logger.info("project_queue: idle project=%s — LLM cache invalidated", project_id)


def maybe_finalize_project_after_document_pipeline(
    source_document_id: UUID,
    *,
    pipeline_ok: bool,
    error_message: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.project_queue_enabled:
        return

    project_id: UUID | None = None
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            return
        if doc.processing_status not in {
            SourceProcessingStatus.PENDING.value,
            SourceProcessingStatus.PROCESSING.value,
        }:
            return
        project_id = doc.project_id
        now = datetime.now(timezone.utc)
        if pipeline_ok:
            doc.processing_status = SourceProcessingStatus.COMPLETED.value
            doc.processing_completed_at = now
            doc.processing_last_error = None
        else:
            doc.processing_status = SourceProcessingStatus.FAILED.value
            doc.processing_last_error = (error_message or "pipeline_failed")[:8000]
            doc.processing_completed_at = now
        session.commit()

    if project_id is None:
        return
    if pipeline_ok:
        _aggregate_project_after_source(project_id)
    _maybe_finalize_project_queue_idle(project_id)
    schedule_project_processing(project_id)


def maybe_finalize_project_after_audio_failure(source_audio_id: UUID, *, error_message: str) -> None:
    settings = get_settings()
    if not settings.project_queue_enabled:
        return

    project_id: UUID | None = None
    with sync_session_scope() as session:
        audio = session.get(SourceAudio, source_audio_id)
        if audio is None:
            return
        if audio.processing_status not in {
            SourceProcessingStatus.PENDING.value,
            SourceProcessingStatus.PROCESSING.value,
        }:
            return
        project_id = audio.project_id
        now = datetime.now(timezone.utc)
        audio.processing_status = SourceProcessingStatus.FAILED.value
        audio.processing_last_error = (error_message or "audio_pipeline_failed")[:8000]
        audio.processing_completed_at = now
        session.commit()

    if project_id is not None:
        _maybe_finalize_project_queue_idle(project_id)
        schedule_project_processing(project_id)


def maybe_finalize_project_after_audio_extract_outcome(
    transcript_id: UUID,
    *,
    pipeline_ok: bool,
    error_message: str | None = None,
) -> None:
    from app.models.transcript import Transcript

    settings = get_settings()
    if not settings.project_queue_enabled:
        return

    project_id: UUID | None = None
    with sync_session_scope() as session:
        tr = session.get(Transcript, transcript_id)
        if tr is None or tr.source_audio_id is None:
            return
        audio = session.get(SourceAudio, tr.source_audio_id)
        if audio is None:
            return
        if audio.processing_status not in {
            SourceProcessingStatus.PENDING.value,
            SourceProcessingStatus.PROCESSING.value,
        }:
            return
        project_id = audio.project_id
        now = datetime.now(timezone.utc)
        if pipeline_ok:
            audio.processing_status = SourceProcessingStatus.COMPLETED.value
            audio.processing_completed_at = now
            audio.processing_last_error = None
        else:
            audio.processing_status = SourceProcessingStatus.FAILED.value
            audio.processing_last_error = (error_message or "transcript_extraction_failed")[:8000]
            audio.processing_completed_at = now
        session.commit()

    if project_id is None:
        return
    if pipeline_ok:
        _aggregate_project_after_source(project_id)
    _maybe_finalize_project_queue_idle(project_id)
    schedule_project_processing(project_id)


def requeue_project_document_pipeline(source_document_id: UUID, *, reason: str, countdown: int = 30) -> None:
    settings = get_settings()
    if not settings.project_queue_enabled:
        return

    project_id: UUID | None = None
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            return
        if doc.processing_status != SourceProcessingStatus.PROCESSING.value:
            return
        project_id = doc.project_id
        doc.processing_status = SourceProcessingStatus.PENDING.value
        doc.processing_last_error = (reason or "document_pipeline_busy")[:8000]
        doc.processing_started_at = None
        session.commit()

    if project_id is not None:
        schedule_project_processing(project_id, countdown=countdown)


def finalize_project_document_pipeline_task_result(source_document_id: UUID, result: dict[str, Any]) -> None:
    st = result.get("status")
    if st == "missing":
        maybe_finalize_project_after_document_pipeline(
            source_document_id,
            pipeline_ok=False,
            error_message="source_document_missing",
        )
        return
    if st == "already_processing":
        requeue_project_document_pipeline(
            source_document_id,
            reason="document pipeline is already running; queued retry",
        )
        return
    ok = st == "ok"
    err = result.get("error")
    maybe_finalize_project_after_document_pipeline(
        source_document_id,
        pipeline_ok=ok,
        error_message=str(err) if err is not None else None,
    )
