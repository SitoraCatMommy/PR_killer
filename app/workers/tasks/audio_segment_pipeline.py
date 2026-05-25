"""Chunked audio transcription: ffmpeg split → per-segment ASR → merge → extract."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select, update

from app.domain.enums import AudioPipelineStatus, AudioSegmentStatus, JobStatus
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.audio_segment import AudioSegment
from app.models.source_audio import SourceAudio
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.services.audio_segment_split_service import split_audio_into_segment_files
from app.services.batch_queue_service import maybe_finalize_batch_after_audio_failure
from app.services.processing_orchestrator_service import ProcessingOrchestratorService
from app.services.transcription_service import TranscriptionService
from app.workers.tasks.research_extraction import extract_entities_for_transcript

logger = logging.getLogger(__name__)

# Gemini inline_data cap (see gemini_provider); must match fast-path size gate.
_GEMINI_INLINE_CAP_BYTES = 18 * 1024 * 1024


def _max_gemini_inline_bytes(settings) -> int:
    return min(int(settings.transcription_max_segment_bytes), _GEMINI_INLINE_CAP_BYTES)


def _audio_duration_seconds(audio: SourceAudio) -> float | None:
    if audio.duration_seconds is None:
        return None
    try:
        return float(audio.duration_seconds)
    except (TypeError, ValueError):
        return None


def should_use_gemini_fast_path(settings, audio: SourceAudio, abs_path: Path) -> bool:
    """One-shot Gemini on original file: duration known and within cap, file fits inline limit."""
    if (settings.research_transcription_provider or "").lower() != "gemini":
        return False
    dur = _audio_duration_seconds(audio)
    if dur is None or dur > float(settings.gemini_transcription_fast_path_max_duration_seconds):
        return False
    if not abs_path.is_file():
        return False
    try:
        sz = int(audio.audio_file_bytes) if audio.audio_file_bytes is not None else int(abs_path.stat().st_size)
    except OSError:
        return False
    return sz > 0 and sz <= _max_gemini_inline_bytes(settings)


def _try_merge_audio(session, source_audio_id: UUID) -> None:
    """When no pending/processing segments remain, merge successful slices or mark failed."""
    st = get_settings()
    n_pending = int(
        session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == source_audio_id,
                AudioSegment.status.in_(("pending", "processing")),
            )
        )
        or 0
    )
    if n_pending > 0:
        return

    n_done = int(
        session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == source_audio_id,
                AudioSegment.status == AudioSegmentStatus.DONE.value,
            )
        )
        or 0
    )
    n_failed = int(
        session.scalar(
            select(func.count())
            .select_from(AudioSegment)
            .where(
                AudioSegment.source_audio_id == source_audio_id,
                AudioSegment.status == AudioSegmentStatus.FAILED.value,
            )
        )
        or 0
    )
    n_total = int(
        session.scalar(
            select(func.count()).select_from(AudioSegment).where(AudioSegment.source_audio_id == source_audio_id)
        )
        or 0
    )
    if n_total == 0:
        return

    audio = session.get(SourceAudio, source_audio_id)
    if audio is None:
        return

    if n_done == 0:
        audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
        audio.audio_pipeline_last_error = "All transcription segments failed"
        session.flush()
        maybe_finalize_batch_after_audio_failure(
            source_audio_id,
            error_message=audio.audio_pipeline_last_error or "all_segments_failed",
        )
        return

    res = session.execute(
        update(SourceAudio)
        .where(
            SourceAudio.id == source_audio_id,
            SourceAudio.audio_pipeline_status == AudioPipelineStatus.TRANSCRIBING.value,
        )
        .values(audio_pipeline_status=AudioPipelineStatus.MERGING.value)
    )
    if res.rowcount == 0:
        return

    rows = list(
        session.scalars(
            select(AudioSegment)
            .where(
                AudioSegment.source_audio_id == source_audio_id,
                AudioSegment.status == AudioSegmentStatus.DONE.value,
            )
            .order_by(AudioSegment.segment_index)
        ).all()
    )
    parts = [str(r.transcript_text or "").strip() for r in rows if (r.transcript_text or "").strip()]
    merged = "\n\n".join(parts)
    if not merged.strip():
        audio = session.get(SourceAudio, source_audio_id)
        if audio:
            audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
            audio.audio_pipeline_last_error = "Merged transcript empty"
        session.flush()
        maybe_finalize_batch_after_audio_failure(source_audio_id, error_message="Merged transcript empty")
        return

    session.execute(delete(Transcript).where(Transcript.source_audio_id == source_audio_id))
    session.execute(delete(TextChunk).where(TextChunk.source_audio_id == source_audio_id))
    session.flush()

    audio = session.get(SourceAudio, source_audio_id)
    provider_from_segments = next((r.provider for r in rows if (r.provider or "").strip()), None)
    tr = Transcript(
        source_audio_id=source_audio_id,
        full_text=merged,
        language=audio.language if audio else None,
        status=JobStatus.COMPLETED,
        provider_name=provider_from_segments or "chunked-asr",
    )
    session.add(tr)
    session.flush()
    preview = merged[:8000] if len(merged) > 8000 else merged
    session.add(
        TranscriptSegment(
            transcript_id=tr.id,
            speaker_label=None,
            start_seconds=Decimal("0"),
            end_seconds=Decimal("0"),
            text=preview,
            confidence_score=None,
        )
    )
    session.flush()

    orch = ProcessingOrchestratorService(st)
    orch.chunk_transcript_sync(session, tr.id, strategy="fixed")

    audio = session.get(SourceAudio, source_audio_id)
    if audio:
        audio.audio_pipeline_status = AudioPipelineStatus.READY.value
        audio.audio_pipeline_last_error = (
            f"{n_failed} segment(s) failed; merged {n_done} slice(s)."
            if n_failed
            else None
        )
    session.flush()
    extract_entities_for_transcript.delay(str(tr.id))
    logger.info(
        "audio_merge_done audio_id=%s transcript_id=%s done=%s failed=%s",
        source_audio_id,
        tr.id,
        n_done,
        n_failed,
    )


@celery_app.task(name="app.workers.tasks.audio_segment_pipeline.transcribe_audio_segment", time_limit=3600)
def transcribe_audio_segment(segment_id: str) -> dict:
    sid = UUID(segment_id)
    st = get_settings()
    tsvc = TranscriptionService(st)
    path: Path | None = None
    lang_hint: str | None = None
    mime_for_asr = "audio/opus"
    with sync_session_scope() as session:
        seg = session.get(AudioSegment, sid)
        if seg is None:
            return {"status": "missing", "segment_id": segment_id}
        if seg.status == AudioSegmentStatus.DONE.value:
            return {"status": "skipped", "segment_id": segment_id}
        audio = session.get(SourceAudio, seg.source_audio_id)
        lang_hint = audio.language if audio else None
        if audio and (audio.mime_type or "").strip():
            mime_for_asr = (audio.mime_type or "").split(";")[0].strip()
        seg.status = AudioSegmentStatus.PROCESSING.value
        seg.error_message = None
        session.flush()
        path = Path(st.upload_storage_path) / seg.segment_path

    data = path.read_bytes() if path and path.is_file() else b""
    try:
        structured = tsvc.transcribe_structured_sync(
            audio_bytes=data,
            mime_type=mime_for_asr,
            language_hint=lang_hint,
            audio_file_path=path if path and path.is_file() else None,
            filename_hint=path.name if path else None,
        )
    except Exception as e:
        logger.exception("transcribe_audio_segment failed segment=%s", segment_id)
        with sync_session_scope() as session:
            seg = session.get(AudioSegment, sid)
            if seg is not None and seg.status != AudioSegmentStatus.DONE.value:
                seg.status = AudioSegmentStatus.FAILED.value
                seg.error_message = str(e)[:4000]
                session.flush()
                _try_merge_audio(session, seg.source_audio_id)
        raise

    text = (structured.full_text or "").strip()
    if not text:
        with sync_session_scope() as session:
            seg = session.get(AudioSegment, sid)
            if seg is not None:
                seg.status = AudioSegmentStatus.FAILED.value
                seg.error_message = "empty_transcription"
                session.flush()
                _try_merge_audio(session, seg.source_audio_id)
        raise RuntimeError("empty_transcription")

    with sync_session_scope() as session:
        seg = session.get(AudioSegment, sid)
        if seg is None:
            return {"status": "missing", "segment_id": segment_id}
        seg.transcript_text = structured.full_text
        seg.provider = structured.provider_name
        seg.status = AudioSegmentStatus.DONE.value
        session.flush()
        _try_merge_audio(session, seg.source_audio_id)

    return {"status": "ok", "segment_id": segment_id}


@celery_app.task(
    name="app.workers.tasks.audio_segment_pipeline.transcribe_full_audio_gemini_fast",
    time_limit=2 * 3600,
    soft_time_limit=110 * 60,
)
def transcribe_full_audio_gemini_fast(source_audio_id: str) -> dict:
    """One segment = original file; transcribe via existing segment worker; merge unchanged."""
    aid = UUID(source_audio_id)
    st = get_settings()
    seg_id: str | None = None
    try:
        with sync_session_scope() as session:
            audio = session.get(SourceAudio, aid)
            if audio is None:
                return {"status": "missing", "source_audio_id": source_audio_id}
            if not audio.original_path:
                split_audio_into_segments.delay(source_audio_id)
                return {"status": "deferred", "source_audio_id": source_audio_id, "mode": "segmented_split"}
            src = Path(st.upload_storage_path) / audio.original_path
            if not should_use_gemini_fast_path(st, audio, src):
                logger.info(
                    "transcription_pipeline_mode=%s source_audio_id=%s detail=%s",
                    "segmented_split",
                    source_audio_id,
                    "fast_path_precheck_failed_inside_task",
                )
                split_audio_into_segments.delay(source_audio_id)
                return {"status": "deferred", "source_audio_id": source_audio_id, "mode": "segmented_split"}

            logger.info(
                "transcription_pipeline_mode=%s source_audio_id=%s duration_sec=%s max_inline_bytes=%s",
                "gemini_fast_path",
                source_audio_id,
                _audio_duration_seconds(audio),
                _max_gemini_inline_bytes(st),
            )

            session.execute(delete(AudioSegment).where(AudioSegment.source_audio_id == aid))
            session.flush()
            audio.audio_pipeline_status = AudioPipelineStatus.TRANSCRIBING.value
            audio.audio_pipeline_last_error = None
            dur_ms = 0
            dsec = _audio_duration_seconds(audio)
            if dsec is not None:
                dur_ms = int(dsec * 1000)
            sg = AudioSegment(
                source_audio_id=aid,
                segment_index=0,
                start_ms=0,
                end_ms=dur_ms,
                segment_path=audio.original_path,
                status=AudioSegmentStatus.PENDING.value,
            )
            session.add(sg)
            session.flush()
            seg_id = str(sg.id)

        seg_result = transcribe_audio_segment.run(seg_id)
        return {
            "status": "ok",
            "source_audio_id": source_audio_id,
            "mode": "gemini_fast_path",
            "segment_result": seg_result,
        }
    except Exception as e:
        logger.warning(
            "transcription_pipeline_mode=%s source_audio_id=%s failing_over_to=%s error=%s",
            "gemini_fast_path",
            source_audio_id,
            "segmented_split",
            str(e)[:800],
            exc_info=True,
        )
        with sync_session_scope() as session:
            audio = session.get(SourceAudio, aid)
            if audio is not None:
                audio.audio_pipeline_last_error = None
            session.execute(delete(AudioSegment).where(AudioSegment.source_audio_id == aid))
            session.flush()
        split_audio_into_segments.delay(source_audio_id)
        return {
            "status": "fallback",
            "source_audio_id": source_audio_id,
            "mode": "segmented_split",
            "message": str(e)[:800],
        }


@celery_app.task(
    name="app.workers.tasks.audio_segment_pipeline.split_audio_into_segments",
    time_limit=4 * 3600,
    soft_time_limit=350 * 60,
)
def split_audio_into_segments(source_audio_id: str) -> dict:
    aid = UUID(source_audio_id)
    st = get_settings()
    seg_ids: list[UUID] = []
    try:
        with sync_session_scope() as session:
            audio = session.get(SourceAudio, aid)
            if audio is None:
                return {"status": "missing", "source_audio_id": source_audio_id}
            if not audio.original_path:
                audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
                audio.audio_pipeline_last_error = "missing_original_path"
                return {"status": "error", "code": "missing_original_path"}

            logger.info(
                "transcription_pipeline_mode=%s source_audio_id=%s",
                "segmented_split",
                source_audio_id,
            )
            audio.audio_pipeline_status = AudioPipelineStatus.SPLITTING.value
            audio.audio_pipeline_last_error = None
            session.flush()

            session.execute(delete(AudioSegment).where(AudioSegment.source_audio_id == aid))
            session.flush()

            src = Path(st.upload_storage_path) / audio.original_path
            if not src.is_file():
                audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
                audio.audio_pipeline_last_error = f"file_not_found:{src}"
                return {"status": "error", "code": "file_not_found"}

            plan = split_audio_into_segment_files(
                settings=st,
                project_id=audio.project_id,
                source_audio_id=aid,
                input_path=src,
            )
            if not plan:
                audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
                audio.audio_pipeline_last_error = "no_segments_produced"
                return {"status": "error", "code": "no_segments"}

            for idx, start_ms, end_ms, rel in plan:
                session.add(
                    AudioSegment(
                        source_audio_id=aid,
                        segment_index=idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        segment_path=rel,
                        status=AudioSegmentStatus.PENDING.value,
                    )
                )
            session.flush()
            audio.audio_pipeline_status = AudioPipelineStatus.TRANSCRIBING.value
            session.flush()
            seg_ids = list(
                session.scalars(
                    select(AudioSegment.id)
                    .where(AudioSegment.source_audio_id == aid)
                    .order_by(AudioSegment.segment_index)
                ).all()
            )
    except Exception as e:
        logger.exception("split_audio_into_segments failed audio=%s", aid)
        with sync_session_scope() as session:
            audio = session.get(SourceAudio, aid)
            if audio is not None:
                audio.audio_pipeline_status = AudioPipelineStatus.FAILED.value
                audio.audio_pipeline_last_error = str(e)[:4000]
        return {"status": "error", "source_audio_id": source_audio_id, "message": str(e)}

    for sgid in seg_ids:
        transcribe_audio_segment.delay(str(sgid))

    logger.info(
        "split_audio_into_segments queued audio=%s segment_jobs=%s",
        source_audio_id,
        len(seg_ids),
    )
    return {"status": "ok", "source_audio_id": source_audio_id, "segments": len(seg_ids)}
