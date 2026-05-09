from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

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
from app.schemas.common import ErrorResponse
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
    file: UploadFile = File(...),
    source_type: SourceType = Form(default=SourceType.UPLOAD),
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
    "/audio/upload",
    response_model=SourceAudioRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio_source(
    project_id: UUID,
    ingestion: IngestionServiceDep,
    projects: ProjectServiceDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    source_type: SourceType = Form(default=SourceType.UPLOAD),
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
