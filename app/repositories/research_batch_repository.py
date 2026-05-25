from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import BatchSourceProcessingStatus
from app.domain.research_languages import normalize_output_language
from app.models.research_batch import ResearchBatch
from app.models.research_batch_source import ResearchBatchSource


class ResearchBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, project_id: UUID, name: str, description: str | None) -> ResearchBatch:
        b = ResearchBatch(project_id=project_id, name=name.strip(), description=(description or "").strip() or None)
        self._session.add(b)
        await self._session.flush()
        return b

    async def get(self, batch_id: UUID) -> ResearchBatch | None:
        stmt = (
            select(ResearchBatch)
            .where(ResearchBatch.id == batch_id)
            .options(selectinload(ResearchBatch.sources))
        )
        return await self._session.scalar(stmt)

    async def list_for_project(self, project_id: UUID, *, offset: int, limit: int) -> tuple[list[ResearchBatch], int]:
        cnt = await self._session.scalar(
            select(func.count()).select_from(ResearchBatch).where(ResearchBatch.project_id == project_id)
        )
        total = int(cnt or 0)
        stmt = (
            select(ResearchBatch)
            .where(ResearchBatch.project_id == project_id)
            .order_by(ResearchBatch.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list((await self._session.scalars(stmt)).all())
        return rows, total

    async def update(self, batch_id: UUID, patch: dict[str, Any]) -> ResearchBatch | None:
        b = await self._session.get(ResearchBatch, batch_id)
        if b is None:
            return None
        if "name" in patch and patch["name"] is not None:
            b.name = str(patch["name"]).strip()[:512]
        if "description" in patch:
            v = patch["description"]
            b.description = None if v is None else (str(v).strip() or None)
        if "output_language" in patch:
            ol = patch["output_language"]
            if ol is None or (isinstance(ol, str) and not str(ol).strip()):
                b.output_language = None
            else:
                b.output_language = normalize_output_language(str(ol), default="ru")
        if "single_file_multi_interview_mode" in patch and patch["single_file_multi_interview_mode"] is not None:
            b.single_file_multi_interview_mode = bool(patch["single_file_multi_interview_mode"])
        await self._session.flush()
        return b

    async def add_document(
        self,
        batch_id: UUID,
        source_document_id: UUID,
        *,
        sort_order: int = 0,
        processing_status: str = BatchSourceProcessingStatus.IDLE.value,
    ) -> ResearchBatchSource:
        row = ResearchBatchSource(
            batch_id=batch_id,
            source_document_id=source_document_id,
            source_audio_id=None,
            sort_order=int(sort_order),
            processing_status=processing_status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_audio(
        self,
        batch_id: UUID,
        source_audio_id: UUID,
        *,
        sort_order: int = 0,
        processing_status: str = BatchSourceProcessingStatus.IDLE.value,
    ) -> ResearchBatchSource:
        row = ResearchBatchSource(
            batch_id=batch_id,
            source_document_id=None,
            source_audio_id=source_audio_id,
            sort_order=int(sort_order),
            processing_status=processing_status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete_source_row(self, batch_id: UUID, source_row_id: UUID) -> bool:
        row = await self._session.get(ResearchBatchSource, source_row_id)
        if row is None or row.batch_id != batch_id:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
