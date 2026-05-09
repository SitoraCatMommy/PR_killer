from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.api.deps import (
    IngestionServiceDep,
    PaginationDep,
    ProjectServiceDep,
    SettingsDep,
    SourceQueryServiceDep,
)
from app.api.upload_utils import read_upload_file_with_limit
from app.domain.enums import SourceType
from app.infrastructure.database import DbSession
from app.infrastructure.settings import get_settings
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.schemas.common import BulkUploadItemResult, BulkUploadResponse, ErrorResponse
from app.schemas.processing import ProcessingTaskQueued
from app.schemas.research_chunk import TextChunkRead
from app.schemas.research_source import (
    RawTextNoteCreate,
    SourceAudioDetailRead,
    SourceAudioRead,
    SourceDocumentDetailRead,
    SourceDocumentRead,
    UnifiedSourcesResponse,
)
from app.workers.tasks.research_extraction import extract_entities_for_document
from app.workers.tasks.research_processing import chunk_source_document, transcribe_audio_source

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
        raise
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
        doc = await ingestion.upload_text_file(
            project_id,
            filename=filename,
            content=data,
            mime_type=file.content_type,
            source_type=source_type,
            extra_metadata={"bulk_upload": True, "original_filename": filename},
        )
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
    task = transcribe_audio_source.delay(str(source_audio_id))
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
