from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MaterialType, ProcessingStatus
from app.models.material import Material


class MaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, material_id: UUID) -> Material | None:
        return await self._session.get(Material, material_id)

    async def create_text(
        self,
        *,
        raw_text: str,
        title: str | None,
        source_uri: str | None,
        mime_type: str | None,
        extra_metadata: dict,
    ) -> Material:
        m = Material(
            material_type=MaterialType.TEXT,
            title=title,
            source_uri=source_uri,
            mime_type=mime_type,
            raw_text=raw_text,
            status=ProcessingStatus.PENDING,
            extra_metadata=extra_metadata,
        )
        self._session.add(m)
        await self._session.flush()
        return m

    async def create_audio_placeholder(
        self,
        *,
        audio_storage_key: str,
        title: str | None,
        source_uri: str | None,
        mime_type: str | None,
        extra_metadata: dict,
    ) -> Material:
        m = Material(
            material_type=MaterialType.AUDIO,
            title=title,
            source_uri=source_uri,
            mime_type=mime_type,
            audio_storage_key=audio_storage_key,
            status=ProcessingStatus.PENDING,
            extra_metadata=extra_metadata,
        )
        self._session.add(m)
        await self._session.flush()
        return m

    async def update_text_fields(
        self,
        material_id: UUID,
        *,
        raw_text: str | None = None,
        normalized_text: str | None = None,
        status: ProcessingStatus | None = None,
        processing_error: str | None = None,
    ) -> Material | None:
        m = await self.get_by_id(material_id)
        if m is None:
            return None
        if raw_text is not None:
            m.raw_text = raw_text
        if normalized_text is not None:
            m.normalized_text = normalized_text
        if status is not None:
            m.status = status
        if processing_error is not None:
            m.processing_error = processing_error
        await self._session.flush()
        return m

    async def list_recent(self, limit: int = 50) -> list[Material]:
        stmt = select(Material).order_by(Material.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
