import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MaterialType, ProcessingStatus
from app.repositories.material_repository import MaterialRepository
from app.services.pipeline_dispatcher import MaterialPipelineDispatcher


class MaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._materials = MaterialRepository(session)

    async def ingest_text(
        self,
        *,
        raw_text: str,
        title: str | None,
        source_uri: str | None,
        mime_type: str | None,
        extra_metadata: dict,
        enqueue_pipeline: bool = True,
    ) -> tuple[UUID, str | None]:
        m = await self._materials.create_text(
            raw_text=raw_text,
            title=title,
            source_uri=source_uri,
            mime_type=mime_type,
            extra_metadata=extra_metadata,
        )
        await self._session.commit()
        task_id = MaterialPipelineDispatcher.enqueue_material_pipeline(m.id) if enqueue_pipeline else None
        return m.id, task_id

    async def ingest_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str | None,
        title: str | None,
        source_uri: str | None,
        mime_type: str | None,
        extra_metadata: dict,
        storage_dir: Path,
        enqueue_pipeline: bool = True,
    ) -> tuple[UUID, str | None]:
        storage_dir.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4()}_{filename or 'audio.bin'}"
        path = storage_dir / key
        path.write_bytes(audio_bytes)
        m = await self._materials.create_audio_placeholder(
            audio_storage_key=str(path),
            title=title,
            source_uri=source_uri,
            mime_type=mime_type,
            extra_metadata=extra_metadata,
        )
        await self._session.commit()
        task_id = MaterialPipelineDispatcher.enqueue_material_pipeline(m.id) if enqueue_pipeline else None
        return m.id, task_id

    async def get(self, material_id: UUID):
        return await self._materials.get_by_id(material_id)

    async def list_recent(self, limit: int = 50):
        return await self._materials.list_recent(limit)

    async def mark_failed(self, material_id: UUID, message: str) -> None:
        await self._materials.update_text_fields(
            material_id,
            status=ProcessingStatus.FAILED,
            processing_error=message,
        )
        await self._session.commit()
