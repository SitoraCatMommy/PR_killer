from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.source_audio import SourceAudio


class SourceAudioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, audio_id: UUID) -> SourceAudio | None:
        return await self._session.get(SourceAudio, audio_id)

    async def belongs_to_project(self, audio_id: UUID, project_id: UUID) -> bool:
        row = await self.get_by_id(audio_id)
        return row is not None and row.project_id == project_id

    async def create(
        self,
        *,
        project_id: UUID,
        filename: str,
        original_path: str | None,
        mime_type: str | None,
        language: str | None,
        metadata_json: dict,
        duration_seconds: Decimal | None = None,
    ) -> SourceAudio:
        a = SourceAudio(
            project_id=project_id,
            filename=filename,
            original_path=original_path,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            language=language,
            metadata_json=metadata_json,
        )
        self._session.add(a)
        await self._session.flush()
        return a

    async def list_by_project(self, project_id: UUID) -> list[SourceAudio]:
        stmt = (
            select(SourceAudio)
            .options(
                load_only(
                    SourceAudio.id,
                    SourceAudio.project_id,
                    SourceAudio.filename,
                    SourceAudio.mime_type,
                    SourceAudio.language,
                    SourceAudio.created_at,
                )
            )
            .where(SourceAudio.project_id == project_id)
            .order_by(SourceAudio.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project_window(
        self,
        project_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> list[SourceAudio]:
        stmt = (
            select(SourceAudio)
            .options(
                load_only(
                    SourceAudio.id,
                    SourceAudio.project_id,
                    SourceAudio.filename,
                    SourceAudio.mime_type,
                    SourceAudio.language,
                    SourceAudio.created_at,
                )
            )
            .where(SourceAudio.project_id == project_id)
            .order_by(SourceAudio.created_at.desc(), SourceAudio.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: UUID) -> int:
        q = await self._session.scalar(
            select(func.count())
            .select_from(SourceAudio)
            .where(SourceAudio.project_id == project_id)
        )
        return int(q or 0)
