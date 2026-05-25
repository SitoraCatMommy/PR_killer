"""Project-level analysis: bulk upload, processing queue, LLM reports, public links."""

from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import IngestionServiceDep, SettingsDep
from app.api.upload_utils import read_upload_file_with_limit
from app.domain.enums import SourceType
from app.domain.research_languages import normalize_output_language
from app.infrastructure.database import DbSession
from app.models.project import Project
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.repositories.project_public_report_repository import ProjectPublicReportRepository
from app.schemas.common import ErrorResponse
from app.schemas.processing import ProcessingTaskQueued
from app.schemas.research_batch import (
    AudiencePortraitResponse,
    BatchDocumentPipelineRecoverResponse,
    BatchPublicLinkResponse,
    BulkUploadResponse,
    BulkUploadResultItem,
    FullReportResponse,
    PRStrategyResponse,
)
from app.schemas.research_project import ProjectProcessingQueueItem, ProjectProcessingQueueResponse
from app.services.docx_text_extraction import DOCX_ERROR_CODES, DOCX_ERROR_MESSAGES_EN
from app.services.project_cached_llm_service import (
    build_project_full_report_response,
    get_or_create_project_audience_portrait_response,
    get_or_create_project_pr_strategy_response,
    invalidate_project_llm_cache,
)
from app.services.batch_document_pipeline_recovery_service import list_project_documents_needing_recovery
from app.services.project_queue_service import (
    fetch_project_queue_summary_async,
    mark_idle_and_failed_sources_pending_async,
    mark_sources_pending_async,
    project_queue_has_active_work,
    schedule_project_processing,
)
from app.services.research_batch_dashboard_service import DASHBOARD_GROUP_BY_FIELDS, is_audio_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["project-analysis"])

_MAX_BULK_FILES = 100
_MAX_PROJECT_SOURCES = 500


async def _ensure_project_queue_idle(
    session: DbSession,
    project_id: UUID,
    *,
    force_while_processing: bool = False,
) -> None:
    if force_while_processing:
        return
    summary = await fetch_project_queue_summary_async(session, project_id)
    if project_queue_has_active_work(summary):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "processing_not_complete",
                "message": "Project sources are still being processed. Wait for the queue to finish.",
                "queue_summary": summary,
            },
        )


async def _project_or_404(session: DbSession, project_id: UUID) -> Project:
    proj = await session.get(Project, project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    return proj


def _validate_segment_query(
    *,
    group_by: str | None,
    segment_value: str | None,
) -> str | None:
    if segment_value is not None and not segment_value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_segment", "message": "segment_value cannot be empty"},
        )
    if segment_value is not None and group_by is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "segment_requires_group_by",
                "message": "segment_value requires group_by",
            },
        )
    if group_by is not None and group_by not in DASHBOARD_GROUP_BY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_group_by",
                "message": f"group_by must be one of: {', '.join(sorted(DASHBOARD_GROUP_BY_FIELDS))}",
            },
        )
    if segment_value is not None and len(segment_value) > 240:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "segment_too_long", "message": "segment_value is too long"},
        )
    return segment_value.strip() if segment_value else None


def _project_output_language(proj: Project) -> str:
    return normalize_output_language(getattr(proj, "output_language", None), default="ru")


@router.post(
    "/{project_id}/sources/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def bulk_upload_project_sources(
    project_id: UUID,
    session: DbSession,
    ingestion: IngestionServiceDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File(description="Interview files (audio or text)")],
    metadata_json: str = Form(default="{}"),
    run_analysis: bool = Form(default=False),
    language: str | None = Form(default=None),
    transcription_language: str | None = Form(default=None),
    source_type: SourceType = Form(default=SourceType.UPLOAD),
    invalidate_llm_cache: bool = Form(
        default=True,
        description="Clear cached audience portrait / PR strategy for this project after upload.",
    ),
) -> BulkUploadResponse:
    await _project_or_404(session, project_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "no_files", "message": "At least one file is required"},
        )
    if len(files) > _MAX_BULK_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "too_many_files",
                "message": f"Maximum {_MAX_BULK_FILES} files per request",
            },
        )

    doc_n = int(
        await session.scalar(
            select(func.count()).select_from(SourceDocument).where(SourceDocument.project_id == project_id)
        )
        or 0
    )
    audio_n = int(
        await session.scalar(
            select(func.count()).select_from(SourceAudio).where(SourceAudio.project_id == project_id)
        )
        or 0
    )
    if doc_n + audio_n + len(files) > _MAX_PROJECT_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "project_capacity",
                "message": f"Project would exceed {_MAX_PROJECT_SOURCES} sources",
            },
        )

    try:
        meta_base = json.loads(metadata_json) if metadata_json.strip() else {}
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_metadata_json", "message": "metadata_json must be valid JSON"},
        ) from e
    if not isinstance(meta_base, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_metadata_json", "message": "metadata_json must be a JSON object"},
        )

    created: list[BulkUploadResultItem] = []
    pipeline_task_ids: list[str] = []
    new_doc_ids: list[UUID] = []
    new_audio_ids: list[UUID] = []
    sort_base = doc_n + audio_n

    for up in files:
        fname = up.filename or "upload"
        try:
            if is_audio_upload(fname, up.content_type):
                audio = await ingestion.upload_audio_file_stream(
                    project_id,
                    upload_file=up,
                    mime_type=up.content_type,
                    language=language,
                    transcription_language=transcription_language,
                    source_type=source_type,
                    extra_metadata=dict(meta_base),
                )
                kind = "audio"
                sid_doc = None
                sid_audio = audio.id
                row_id = audio.id
                new_audio_ids.append(audio.id)
            else:
                data = await read_upload_file_with_limit(
                    up, max_bytes=settings.upload_max_bytes
                )
                doc = await ingestion.upload_text_file(
                    project_id,
                    filename=fname,
                    content=data,
                    mime_type=up.content_type,
                    source_type=source_type,
                    extra_metadata=dict(meta_base),
                )
                kind = "document"
                sid_doc = doc.id
                sid_audio = None
                row_id = doc.id
                new_doc_ids.append(doc.id)
        except ValueError as e:
            code = str(e)
            if code == "project_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "project_not_found", "message": "Project not found"},
                ) from e
            if code in DOCX_ERROR_CODES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": code, "message": DOCX_ERROR_MESSAGES_EN.get(code, code)},
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ingestion_failed", "message": str(e)},
            ) from e

        await session.commit()
        created.append(
            BulkUploadResultItem(
                source_kind=kind,  # type: ignore[arg-type]
                source_row_id=row_id,
                source_document_id=sid_doc,
                source_audio_id=sid_audio,
            )
        )

    if created and invalidate_llm_cache:
        try:
            await invalidate_project_llm_cache(session, project_id)
        except Exception:
            logger.exception(
                "bulk_upload_project_sources: invalidate_project_llm_cache failed project_id=%s",
                project_id,
            )
            await session.rollback()

    if run_analysis and created:
        try:
            await mark_sources_pending_async(
                session,
                document_ids=new_doc_ids,
                audio_ids=new_audio_ids,
                sort_base=sort_base,
            )
            await session.commit()
            schedule_project_processing(project_id)
            pipeline_task_ids.append("project_processing_queue")
        except Exception:
            logger.exception(
                "bulk_upload_project_sources: failed to enqueue project processing project_id=%s",
                project_id,
            )

    return BulkUploadResponse(created=created, pipeline_task_ids=pipeline_task_ids)


@router.post(
    "/{project_id}/process",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}},
)
async def queue_process_project(project_id: UUID, session: DbSession) -> ProcessingTaskQueued:
    await _project_or_404(session, project_id)
    try:
        await mark_idle_and_failed_sources_pending_async(session, project_id)
        await session.commit()
        schedule_project_processing(project_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "queue_failed", "message": str(e)},
        ) from e
    return ProcessingTaskQueued(task_id=f"project:{project_id}", status="queued")


@router.get(
    "/{project_id}/audience-portrait",
    response_model=AudiencePortraitResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_project_audience_portrait(
    project_id: UUID,
    session: DbSession,
    recalculate: bool = Query(default=False),
    force_while_processing: bool = Query(default=False),
    group_by: str | None = Query(default=None),
    segment_value: str | None = Query(default=None),
) -> AudiencePortraitResponse:
    seg = _validate_segment_query(group_by=group_by, segment_value=segment_value)
    proj = await _project_or_404(session, project_id)
    await _ensure_project_queue_idle(session, project_id, force_while_processing=force_while_processing)
    lang = _project_output_language(proj)
    try:
        return await get_or_create_project_audience_portrait_response(
            session,
            project_id,
            group_by=group_by,
            segment_value=seg,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for audience portrait",
                },
            ) from e
        if str(e) == "project_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "portrait_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "portrait_generation_failed", "message": str(e)},
        ) from e


@router.get(
    "/{project_id}/pr-strategy",
    response_model=PRStrategyResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_project_pr_strategy(
    project_id: UUID,
    session: DbSession,
    recalculate: bool = Query(default=False),
    force_while_processing: bool = Query(default=False),
    group_by: str | None = Query(default=None),
    segment_value: str | None = Query(default=None),
) -> PRStrategyResponse:
    seg = _validate_segment_query(group_by=group_by, segment_value=segment_value)
    proj = await _project_or_404(session, project_id)
    await _ensure_project_queue_idle(session, project_id, force_while_processing=force_while_processing)
    lang = _project_output_language(proj)
    try:
        return await get_or_create_project_pr_strategy_response(
            session,
            project_id,
            group_by=group_by,
            segment_value=seg,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for PR strategy",
                },
            ) from e
        if str(e) == "project_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "pr_strategy_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "pr_strategy_generation_failed", "message": str(e)},
        ) from e


@router.get(
    "/{project_id}/full-report",
    response_model=FullReportResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def get_project_full_report(
    project_id: UUID,
    session: DbSession,
    recalculate: bool = Query(default=False),
    force_while_processing: bool = Query(default=False),
) -> FullReportResponse:
    proj = await _project_or_404(session, project_id)
    await _ensure_project_queue_idle(session, project_id, force_while_processing=force_while_processing)
    lang = _project_output_language(proj)
    try:
        return await build_project_full_report_response(
            session,
            project_id,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for full report",
                },
            ) from e
        if str(e) == "project_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "full_report_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "full_report_generation_failed", "message": str(e)},
        ) from e


@router.get(
    "/{project_id}/processing-queue",
    response_model=ProjectProcessingQueueResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_project_processing_queue(
    project_id: UUID,
    session: DbSession,
) -> ProjectProcessingQueueResponse:
    await _project_or_404(session, project_id)
    summary = await fetch_project_queue_summary_async(session, project_id)
    docs = list(
        (await session.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id))).all()
    )
    audios = list(
        (await session.scalars(select(SourceAudio).where(SourceAudio.project_id == project_id))).all()
    )
    sources = [
        ProjectProcessingQueueItem(
            kind="document",
            id=str(d.id),
            filename=d.filename,
            processing_status=d.processing_status,
            processing_last_error=d.processing_last_error,
        )
        for d in docs
    ] + [
        ProjectProcessingQueueItem(
            kind="audio",
            id=str(a.id),
            filename=a.filename,
            processing_status=a.processing_status,
            processing_last_error=a.processing_last_error,
        )
        for a in audios
    ]
    return ProjectProcessingQueueResponse(
        idle=int(summary.get("idle") or 0),
        pending=int(summary.get("pending") or 0),
        processing=int(summary.get("processing") or 0),
        completed=int(summary.get("completed") or 0),
        failed=int(summary.get("failed") or 0),
        currently_processing=list(summary.get("currently_processing") or []),
        sources=sources,
    )


@router.post(
    "/{project_id}/documents/recover-pipeline",
    response_model=BatchDocumentPipelineRecoverResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}},
)
async def recover_project_document_pipeline(
    project_id: UUID,
    session: DbSession,
) -> BatchDocumentPipelineRecoverResponse:
    """Re-queue chunk+extract for project documents stuck in failed/intermediate states."""
    from app.domain.enums import SourceProcessingStatus

    await _project_or_404(session, project_id)
    queued, skipped = await list_project_documents_needing_recovery(session, project_id)
    task_ids: list[str] = []
    if queued:
        for i, did in enumerate(queued):
            doc = await session.get(SourceDocument, did)
            if doc is None:
                continue
            doc.processing_status = SourceProcessingStatus.PENDING.value
            doc.processing_sort_order = 10_000 + i
            doc.processing_last_error = None
            doc.processing_started_at = None
            doc.processing_completed_at = None
        await session.commit()
        schedule_project_processing(project_id)
        task_ids.append("project_processing_queue")
    return BatchDocumentPipelineRecoverResponse(
        queued_document_ids=queued,
        skipped_document_ids=skipped,
        pipeline_task_ids=task_ids,
    )


@router.post(
    "/{project_id}/public-link",
    response_model=BatchPublicLinkResponse,
    responses={404: {"model": ErrorResponse}},
)
async def create_project_public_link(
    project_id: UUID,
    session: DbSession,
    settings: SettingsDep,
) -> BatchPublicLinkResponse:
    await _project_or_404(session, project_id)
    repo = ProjectPublicReportRepository(session)
    row = await repo.upsert_for_project(project_id)
    await session.commit()
    prefix = settings.api_v1_prefix.rstrip("/")
    return BatchPublicLinkResponse(
        token=row.token,
        report_path=f"{prefix}/report/public/{row.token}",
    )
