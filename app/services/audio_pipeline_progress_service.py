"""Aggregate audio ingestion / chunked transcription progress for API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import AudioPipelineStatus, AudioSegmentStatus
from app.models.audio_segment import AudioSegment
from app.models.research_batch import ResearchBatch
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.repositories.interview_unit_repository import count_units_for_documents
from app.schemas.audio_pipeline import (
    AudioPipelineProgressRead,
    BatchAudioPipelineItemRead,
    BatchAudioPipelineResponse,
    BatchAudioPipelineSummary,
)


def _chunk_progress_percent(*, n_total: int, n_done: int, n_failed: int) -> int:
    if n_total < 1:
        return 0
    if n_done + n_failed >= n_total and n_total > 0 and n_done > 0:
        return min(100, int(100.0 * n_done / n_total + 0.5))
    return min(100, int(100.0 * n_done / n_total + 0.5))


def _ui_stage_and_progress(
    audio: SourceAudio,
    *,
    n_total: int,
    n_done: int,
    n_failed: int,
    n_pending: int,
    n_processing: int,
) -> tuple[str, int]:
    """
    Exposed pipeline_stage:
    uploaded | splitting | transcribing | analyzing | done | failed
    """
    st = (audio.audio_pipeline_status or "").lower()
    if st == AudioPipelineStatus.FAILED.value or (n_total > 0 and n_done + n_failed >= n_total and n_done == 0 and n_failed == n_total):
        return "failed", 0
    if st == AudioPipelineStatus.READY.value:
        return "done", 100
    pct = _chunk_progress_percent(n_total=n_total, n_done=n_done, n_failed=n_failed)
    if st == AudioPipelineStatus.UPLOADED.value:
        return "uploaded", 0
    if st == AudioPipelineStatus.SPLITTING.value:
        return "splitting", pct
    if st == AudioPipelineStatus.TRANSCRIBING.value:
        return "transcribing", pct
    if st == AudioPipelineStatus.MERGING.value:
        return "analyzing", max(pct, 90 if n_total and n_done >= n_total else pct)
    if st == "unknown" or not st:
        return "uploaded", pct
    return (st if st in {"uploaded", "splitting", "transcribing", "analyzing", "done", "failed"} else st), pct


async def build_audio_progress(session: AsyncSession, audio_id: UUID) -> AudioPipelineProgressRead | None:
    audio = await session.get(SourceAudio, audio_id)
    if audio is None:
        return None
    n_total = int(
        await session.scalar(
            select(func.count()).select_from(AudioSegment).where(AudioSegment.source_audio_id == audio_id)
        )
        or 0
    )
    n_done = int(
        await session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == audio_id,
                AudioSegment.status == AudioSegmentStatus.DONE.value,
            )
        )
        or 0
    )
    n_failed = int(
        await session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == audio_id,
                AudioSegment.status == AudioSegmentStatus.FAILED.value,
            )
        )
        or 0
    )
    n_pending = int(
        await session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == audio_id,
                AudioSegment.status == AudioSegmentStatus.PENDING.value,
            )
        )
        or 0
    )
    n_processing = int(
        await session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == audio_id,
                AudioSegment.status == AudioSegmentStatus.PROCESSING.value,
            )
        )
        or 0
    )
    ps, ppct = _ui_stage_and_progress(
        audio,
        n_total=n_total,
        n_done=n_done,
        n_failed=n_failed,
        n_pending=n_pending,
        n_processing=n_processing,
    )
    if ps == "done":
        ppct = 100
    if ps == "failed":
        ppct = 0

    overall = audio.audio_pipeline_status or AudioPipelineStatus.READY.value

    return AudioPipelineProgressRead(
        source_audio_id=audio.id,
        filename=audio.filename,
        overall_status=overall,
        total_chunks=n_total,
        done_chunks=n_done,
        failed_chunks=n_failed,
        current_stage=ps,
        last_error=audio.audio_pipeline_last_error,
        pipeline_stage=ps,
        progress_percent=ppct,
    )


async def _interview_rollup(session: AsyncSession, batch: ResearchBatch) -> dict[str, Any]:
    total_i = 0
    proc_i = 0
    err_n = 0
    doc_ids = [s.source_document_id for s in batch.sources if s.source_document_id]
    multi = getattr(batch, "single_file_multi_interview_mode", True) is not False
    for did in doc_ids:
        doc = await session.get(SourceDocument, did)
        if doc is None:
            continue
        phase = str((doc.pipeline_state_json or {}).get("phase") or "").lower()
        n_u = await count_units_for_documents(session, [did])
        is_done = phase == "extracted"
        if multi and n_u > 0:
            total_i += n_u
            proc_i += n_u if is_done else 0
        else:
            total_i += 1
            proc_i += 1 if is_done else 0

    for s in batch.sources:
        if not s.source_audio_id:
            continue
        total_i += 1
        a = await session.get(SourceAudio, s.source_audio_id)
        if a is None:
            err_n += 1
            continue
        st = (a.audio_pipeline_status or "").lower()
        if st == AudioPipelineStatus.READY.value:
            proc_i += 1
        elif st == AudioPipelineStatus.FAILED.value:
            err_n += 1

    return {
        "total_interviews": total_i,
        "processed_interviews": proc_i,
        "errors_count": err_n,
    }


async def build_batch_audio_pipeline(session: AsyncSession, batch_id: UUID) -> BatchAudioPipelineResponse | None:
    stmt = (
        select(ResearchBatch)
        .where(ResearchBatch.id == batch_id)
        .options(selectinload(ResearchBatch.sources))
    )
    batch = await session.scalar(stmt)
    if batch is None:
        return None
    audio_ids: list[UUID] = []
    for row in batch.sources:
        if row.source_audio_id:
            audio_ids.append(row.source_audio_id)
    items: list[BatchAudioPipelineItemRead] = []
    ready = failed = inprog = 0
    for aid in audio_ids:
        p = await build_audio_progress(session, aid)
        if p is None:
            continue
        st = (p.overall_status or "").lower()
        if st == AudioPipelineStatus.READY.value:
            ready += 1
        elif st == AudioPipelineStatus.FAILED.value:
            failed += 1
        else:
            inprog += 1
        items.append(
            BatchAudioPipelineItemRead(
                source_audio_id=p.source_audio_id or aid,
                filename=p.filename,
                overall_status=p.overall_status,
                total_chunks=p.total_chunks,
                done_chunks=p.done_chunks,
                failed_chunks=p.failed_chunks,
                current_stage=p.current_stage,
                last_error=p.last_error,
                pipeline_stage=p.pipeline_stage,
                progress_percent=p.progress_percent,
            )
        )
    rollup = await _interview_rollup(session, batch)
    summary = BatchAudioPipelineSummary(
        total_audios=len(items),
        ready=ready,
        failed=failed,
        in_progress=inprog,
        total_interviews=rollup["total_interviews"],
        processed_interviews=rollup["processed_interviews"],
        errors_count=rollup["errors_count"],
    )
    return BatchAudioPipelineResponse(
        batch_id=batch_id,
        items=items,
        summary=summary,
        meta={"batch_name": batch.name, **rollup},
    )
