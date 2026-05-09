from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import MaterialServiceDep, SettingsDep
from app.api.upload_utils import read_upload_file_with_limit
from app.domain.enums import MaterialType
from app.schemas.common import MessageResponse
from app.schemas.material import MaterialCreate, MaterialRead

router = APIRouter()

AudioUploadFile = Annotated[UploadFile, File()]
OptionalFormString = Annotated[str | None, Form()]


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
    import json

    meta: dict = {}
    if extra_metadata:
        try:
            meta = json.loads(extra_metadata)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"invalid extra_metadata json: {e}") from e

    data = await read_upload_file_with_limit(file, max_bytes=settings.upload_max_bytes)
    storage_root = Path("/data/uploads")
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
