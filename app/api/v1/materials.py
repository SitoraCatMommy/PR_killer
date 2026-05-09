from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.api.deps import MaterialServiceDep, SettingsDep
from app.api.upload_utils import read_upload_file_with_limit
from app.domain.enums import MaterialType
from app.schemas.common import BulkUploadItemResult, BulkUploadResponse, MessageResponse
from app.schemas.material import MaterialCreate, MaterialRead

router = APIRouter()

AudioUploadFile = Annotated[UploadFile, File()]
AudioUploadFiles = Annotated[list[UploadFile], File()]
OptionalFormString = Annotated[str | None, Form()]


def _parse_extra_metadata(raw: str | None) -> dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid extra_metadata json: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="extra_metadata must be a JSON object")
    return parsed


def _title_for_audio_file(filename: str | None, title: str | None, file_count: int) -> str | None:
    clean_title = (title or "").strip()
    if clean_title and file_count == 1:
        return clean_title
    if filename:
        return Path(filename).stem or filename
    return clean_title or None


@router.post("/text", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def ingest_text(body: MaterialCreate, svc: MaterialServiceDep) -> MaterialRead:
    if body.material_type is not MaterialType.TEXT:
        raise HTTPException(status_code=400, detail="material_type must be text")
    if not body.raw_text or not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is required")
    material_id, _task_id = await svc.ingest_text(
        raw_text=body.raw_text,
        title=body.title,
        source_uri=body.source_uri,
        mime_type=body.mime_type,
        extra_metadata=body.extra_metadata,
    )
    m = await svc.get(material_id)
    if m is None:
        raise HTTPException(status_code=500, detail="material not found after create")
    return MaterialRead.model_validate(m)


@router.post("/audio", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def ingest_audio(
    svc: MaterialServiceDep,
    settings: SettingsDep,
    file: AudioUploadFile,
    title: OptionalFormString = None,
    source_uri: OptionalFormString = None,
    extra_metadata: OptionalFormString = None,
) -> MaterialRead:
    meta = _parse_extra_metadata(extra_metadata)

    data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
    storage_root = Path(settings.upload_storage_path)
    material_id, _task_id = await svc.ingest_audio(
        audio_bytes=data,
        filename=file.filename,
        title=title,
        source_uri=source_uri,
        mime_type=file.content_type,
        extra_metadata=meta,
        storage_dir=storage_root,
    )
    m = await svc.get(material_id)
    if m is None:
        raise HTTPException(status_code=500, detail="material not found after create")
    return MaterialRead.model_validate(m)


@router.post("/audio/bulk", response_model=BulkUploadResponse)
async def ingest_audio_bulk(
    response: Response,
    svc: MaterialServiceDep,
    settings: SettingsDep,
    files: AudioUploadFiles,
    title: OptionalFormString = None,
    source_uri: OptionalFormString = None,
    extra_metadata: OptionalFormString = None,
) -> BulkUploadResponse:
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

    common_meta = _parse_extra_metadata(extra_metadata)
    storage_root = Path(settings.upload_storage_path)
    items: list[BulkUploadItemResult] = []
    for file in files:
        filename = file.filename or "audio.bin"
        try:
            data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {}
            items.append(
                BulkUploadItemResult(
                    filename=filename,
                    status="error",
                    error_code=str(detail.get("code") or e.status_code),
                    error_message=str(detail.get("message") or e.detail),
                )
            )
            continue

        meta = dict(common_meta)
        meta.setdefault("original_filename", filename)
        meta.setdefault("bulk_upload", True)
        material_id, task_id = await svc.ingest_audio(
            audio_bytes=data,
            filename=filename,
            title=_title_for_audio_file(filename, title, len(files)),
            source_uri=source_uri,
            mime_type=file.content_type,
            extra_metadata=meta,
            storage_dir=storage_root,
        )
        items.append(
            BulkUploadItemResult(
                filename=filename,
                status="ok",
                id=material_id,
                task_id=task_id,
            )
        )

    failed = sum(1 for item in items if item.status != "ok")
    response.status_code = (
        status.HTTP_207_MULTI_STATUS if failed else status.HTTP_201_CREATED
    )
    return BulkUploadResponse(
        total=len(items),
        succeeded=len(items) - failed,
        failed=failed,
        items=items,
    )


@router.get("", response_model=list[MaterialRead])
async def list_materials(
    svc: MaterialServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[MaterialRead]:
    rows = await svc.list_recent(limit=limit)
    return [MaterialRead.model_validate(r) for r in rows]


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(material_id: UUID, svc: MaterialServiceDep) -> MaterialRead:
    m = await svc.get(material_id)
    if m is None:
        raise HTTPException(status_code=404, detail="material not found")
    return MaterialRead.model_validate(m)


@router.post("/{material_id}/reprocess", response_model=MessageResponse)
async def reprocess_material(material_id: UUID, svc: MaterialServiceDep) -> MessageResponse:
    from app.services.pipeline_dispatcher import MaterialPipelineDispatcher

    m = await svc.get(material_id)
    if m is None:
        raise HTTPException(status_code=404, detail="material not found")
    task_id = MaterialPipelineDispatcher.enqueue_material_pipeline(material_id)
    return MessageResponse(message=f"queued task {task_id}")
