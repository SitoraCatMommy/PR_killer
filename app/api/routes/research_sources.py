from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import (
    IngestionServiceDep,
    PaginationDep,
    ProjectServiceDep,
    SettingsDep,
    SourceQueryServiceDep,
)
from app.api.upload_utils import http_exception_for_ingestion_value_error, read_upload_file_with_limit
from app.domain.enums import JobStatus, SourceType
from app.infrastructure.database import DbSession
from app.infrastructure.settings import get_settings
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.transcript import Transcript
from app.schemas.common import BulkUploadItemResult, BulkUploadResponse, ErrorResponse
from app.schemas.processing import ProcessingTaskQueued
from app.schemas.audio_pipeline import AudioPipelineProgressRead
from app.schemas.research_chunk import TextChunkRead
from app.schemas.research_source import (
    RawTextNoteCreate,
    SourceAudioDetailRead,
    SourceAudioRead,
    SourceDocumentDetailRead,
    SourceDocumentRead,
    TranscriptPromoteRequest,
    TranscriptPromoteResponse,
    UnifiedSourcesResponse,
)
from app.repositories.research_batch_repository import ResearchBatchRepository
from app.services.audio_pipeline_progress_service import build_audio_progress
from app.services.transcript_export_service import (
    build_transcript_docx_bytes,
    build_transcript_txt_bytes,
    safe_export_stem,
)
from app.workers.tasks.audio_segment_pipeline import transcribe_full_audio_gemini_fast
from app.workers.tasks.research_extraction import extract_entities_for_document
from app.workers.tasks.research_processing import chunk_source_document

router_nested = APIRouter(
    prefix="/projects/{project_id}/sources",
    tags=["research-sources"],
)

router_detail = APIRouter(prefix="/sources", tags=["research-source-details"])

SourceUploadFile = Annotated[UploadFile, File()]
SourceUploadFiles = Annotated[list[UploadFile], File()]
SourceTypeForm = Annotated[SourceType, Form()]
LanguageForm = Annotated[str | None, Form()]


def _project_404():
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "project_not_found", "message": "Project not found"},
    )


@router_nested.post(
    "/text/upload",
    response_model=SourceDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_text_source(
    project_id: UUID,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
    settings: SettingsDep,
    file: SourceUploadFile,
    source_type: SourceTypeForm = SourceType.UPLOAD,
) -> SourceDocumentRead:
    if await projects.get(project_id) is None:
        raise _project_404()
    data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
    try:
        doc = await ingestion.upload_text_file(
            project_id,
            filename=file.filename or "upload.txt",
            content=data,
            mime_type=file.content_type,
            source_type=source_type,
        )
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise http_exception_for_ingestion_value_error(e) from e
    return SourceDocumentRead.model_validate(doc)


@router_nested.post(
    "/text/upload/bulk",
    response_model=BulkUploadResponse,
)
async def upload_text_sources_bulk(
    project_id: UUID,
    response: Response,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
    settings: SettingsDep,
    files: SourceUploadFiles,
    source_type: SourceTypeForm = SourceType.UPLOAD,
) -> BulkUploadResponse:
    if await projects.get(project_id) is None:
        raise _project_404()
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    if len(files) > settings.upload_max_files:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "too_many_files",
                "message": f"At most {settings.upload_max_files} files can be uploaded at once.",
                "max_files": settings.upload_max_files,
            },
        )

    items: list[BulkUploadItemResult] = []
    for file in files:
        filename = file.filename or "upload.txt"
        try:
            data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {}
            items.append(
                BulkUploadItemResult(
                    filename=filename,
                    status="error",
                    source_kind="document",
                    error_code=str(detail.get("code") or e.status_code),
                    error_message=str(detail.get("message") or e.detail),
                )
            )
            continue
        try:
            doc = await ingestion.upload_text_file(
                project_id,
                filename=filename,
                content=data,
                mime_type=file.content_type,
                source_type=source_type,
                extra_metadata={"bulk_upload": True, "original_filename": filename},
            )
        except ValueError as e:
            if str(e) == "project_not_found":
                raise _project_404() from e
            http_exc = http_exception_for_ingestion_value_error(e)
            detail = http_exc.detail if isinstance(http_exc.detail, dict) else {}
            items.append(
                BulkUploadItemResult(
                    filename=filename,
                    status="error",
                    source_kind="document",
                    error_code=str(detail.get("code") or http_exc.status_code),
                    error_message=str(detail.get("message") or http_exc.detail),
                )
            )
            continue
        items.append(
            BulkUploadItemResult(
                filename=filename,
                status="ok",
                id=doc.id,
                source_kind="document",
            )
        )

    failed = sum(1 for item in items if item.status != "ok")
    response.status_code = status.HTTP_207_MULTI_STATUS if failed else status.HTTP_201_CREATED
    return BulkUploadResponse(
        total=len(items),
        succeeded=len(items) - failed,
        failed=failed,
        items=items,
    )


@router_nested.post(
    "/audio/upload",
    response_model=SourceAudioRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio_source(
    project_id: UUID,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
    settings: SettingsDep,
    file: SourceUploadFile,
    language: LanguageForm = None,
    source_type: SourceTypeForm = SourceType.UPLOAD,
) -> SourceAudioRead:
    if await projects.get(project_id) is None:
        raise _project_404()
    data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
    try:
        audio = await ingestion.upload_audio_file(
            project_id,
            filename=file.filename or "upload.bin",
            content=data,
            mime_type=file.content_type,
            language=language,
            source_type=source_type,
        )
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise
    return SourceAudioRead.model_validate(audio)


@router_nested.post(
    "/audio/upload/bulk",
    response_model=BulkUploadResponse,
)
async def upload_audio_sources_bulk(
    project_id: UUID,
    response: Response,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
    settings: SettingsDep,
    files: SourceUploadFiles,
    language: LanguageForm = None,
    source_type: SourceTypeForm = SourceType.UPLOAD,
) -> BulkUploadResponse:
    if await projects.get(project_id) is None:
        raise _project_404()
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    if len(files) > settings.upload_max_files:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "too_many_files",
                "message": f"At most {settings.upload_max_files} files can be uploaded at once.",
                "max_files": settings.upload_max_files,
            },
        )

    items: list[BulkUploadItemResult] = []
    for file in files:
        filename = file.filename or "upload.bin"
        try:
            data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {}
            items.append(
                BulkUploadItemResult(
                    filename=filename,
                    status="error",
                    source_kind="audio",
                    error_code=str(detail.get("code") or e.status_code),
                    error_message=str(detail.get("message") or e.detail),
                )
            )
            continue
        audio = await ingestion.upload_audio_file(
            project_id,
            filename=filename,
            content=data,
            mime_type=file.content_type,
            language=language,
            source_type=source_type,
            extra_metadata={"bulk_upload": True, "original_filename": filename},
        )
        items.append(
            BulkUploadItemResult(
                filename=filename,
                status="ok",
                id=audio.id,
                source_kind="audio",
            )
        )

    failed = sum(1 for item in items if item.status != "ok")
    response.status_code = status.HTTP_207_MULTI_STATUS if failed else status.HTTP_201_CREATED
    return BulkUploadResponse(
        total=len(items),
        succeeded=len(items) - failed,
        failed=failed,
        items=items,
    )


@router_nested.post(
    "/text/raw",
    response_model=SourceDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_raw_text_note(
    project_id: UUID,
    body: RawTextNoteCreate,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
) -> SourceDocumentRead:
    if await projects.get(project_id) is None:
        raise _project_404()
    try:
        doc = await ingestion.create_raw_text_note(
            project_id,
            title_or_filename=body.title,
            raw_text=body.text,
            extra_metadata=body.metadata_json,
        )
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise
    return SourceDocumentRead.model_validate(doc)


@router_nested.get("", response_model=UnifiedSourcesResponse)
async def list_project_sources(
    project_id: UUID,
    query: SourceQueryServiceDep,
    pagination: PaginationDep,
) -> UnifiedSourcesResponse:
    try:
        return await query.list_unified_sources(
            project_id,
            offset=pagination.offset,
            limit=pagination.limit,
        )
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise


@router_detail.get(
    "/documents/{source_document_id}",
    response_model=SourceDocumentDetailRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_source_document(
    source_document_id: UUID,
    query: SourceQueryServiceDep,
) -> SourceDocumentDetailRead:
    detail = await query.get_document_detail(source_document_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_document_not_found", "message": "Source document not found"},
        )
    return detail


@router_detail.get(
    "/documents/{source_document_id}/chunks",
    response_model=list[TextChunkRead],
    responses={404: {"model": ErrorResponse}},
)
async def list_source_document_chunks(
    source_document_id: UUID,
    query: SourceQueryServiceDep,
) -> list[TextChunkRead]:
    chunks = await query.list_document_chunks(source_document_id)
    if chunks is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_document_not_found", "message": "Source document not found"},
        )
    return chunks


@router_detail.get(
    "/audios/{source_audio_id}",
    response_model=SourceAudioDetailRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_source_audio(
    source_audio_id: UUID,
    query: SourceQueryServiceDep,
) -> SourceAudioDetailRead:
    detail = await query.get_audio_detail(source_audio_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    return detail


@router_detail.post(
    "/audios/{source_audio_id}/transcribe",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_transcribe_audio(
    source_audio_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    row = await session.get(SourceAudio, source_audio_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    task = transcribe_full_audio_gemini_fast.delay(str(source_audio_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router_detail.post(
    "/documents/{source_document_id}/chunk",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_chunk_document(
    source_document_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    row = await session.get(SourceDocument, source_document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_document_not_found", "message": "Source document not found"},
        )
    task = chunk_source_document.delay(str(source_document_id), "fixed")
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router_detail.post(
    "/documents/{source_document_id}/chunk/semantic",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_chunk_document_semantic(
    source_document_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    if not (get_settings().openai_api_key or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "openai_not_configured",
                "message": "Set OPENAI_API_KEY to use semantic (OpenAI) chunking.",
            },
        )
    row = await session.get(SourceDocument, source_document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_document_not_found", "message": "Source document not found"},
        )
    task = chunk_source_document.delay(str(source_document_id), "openai")
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router_detail.post(
    "/documents/{source_document_id}/extract",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_extract_document(
    source_document_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    row = await session.get(SourceDocument, source_document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_document_not_found", "message": "Source document not found"},
        )
    task = extract_entities_for_document.delay(str(source_document_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router_detail.get(
    "/audios/{source_audio_id}/progress",
    response_model=AudioPipelineProgressRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_source_audio_progress(
    source_audio_id: UUID,
    session: DbSession,
) -> AudioPipelineProgressRead:
    audio = await session.get(SourceAudio, source_audio_id)
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    prog = await build_audio_progress(session, source_audio_id)
    if prog is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    return prog


@router_detail.get(
    "/audios/{source_audio_id}/transcript/export",
    responses={404: {"model": ErrorResponse}},
)
async def export_audio_transcript(
    source_audio_id: UUID,
    session: DbSession,
    export_format: Literal["txt", "docx"] = Query("txt", alias="format"),
) -> Response:
    audio = await session.get(SourceAudio, source_audio_id)
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    stmt = (
        select(Transcript)
        .where(
            Transcript.source_audio_id == source_audio_id,
            Transcript.status == JobStatus.COMPLETED,
        )
        .order_by(Transcript.updated_at.desc())
        .limit(1)
    )
    tr = await session.scalar(stmt)
    if tr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "transcript_not_found", "message": "No completed transcript for this audio"},
        )
    stem = safe_export_stem(audio.filename or "transcript")
    if export_format == "txt":
        payload = build_transcript_txt_bytes(tr.full_text)
        return Response(
            content=payload,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}.txt"'},
        )
    payload = build_transcript_docx_bytes(title=stem, full_text=tr.full_text)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{stem}.docx"'},
    )


@router_detail.post(
    "/audios/{source_audio_id}/transcript/promote",
    response_model=TranscriptPromoteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
)
async def promote_audio_transcript_to_document(
    source_audio_id: UUID,
    body: TranscriptPromoteRequest,
    session: DbSession,
    ingestion: IngestionServiceDep,
) -> TranscriptPromoteResponse:
    audio = await session.get(SourceAudio, source_audio_id)
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_audio_not_found", "message": "Source audio not found"},
        )
    if body.target_project_id != audio.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "project_mismatch",
                "message": "target_project_id must match the audio's project",
            },
        )
    stmt = (
        select(Transcript)
        .where(
            Transcript.source_audio_id == source_audio_id,
            Transcript.status == JobStatus.COMPLETED,
        )
        .order_by(Transcript.updated_at.desc())
        .limit(1)
    )
    tr = await session.scalar(stmt)
    if tr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "transcript_not_found", "message": "No completed transcript for this audio"},
        )
    stem = safe_export_stem(body.filename_stem)
    meta = {
        "promoted_from_audio_id": str(source_audio_id),
        "promoted_from_transcript_id": str(tr.id),
    }
    doc = await ingestion.create_raw_text_note(
        body.target_project_id,
        title_or_filename=f"{stem}.txt",
        raw_text=tr.full_text,
        source_type=SourceType.IMPORT,
        extra_metadata=meta,
    )
    if body.research_batch_id is not None:
        repo = ResearchBatchRepository(session)
        batch = await repo.get(body.research_batch_id)
        if batch is None or batch.project_id != body.target_project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "batch_not_found", "message": "Batch not found for this project"},
            )
        await repo.add_document(batch.id, doc.id)
        await session.commit()
    return TranscriptPromoteResponse(source_document_id=doc.id)
