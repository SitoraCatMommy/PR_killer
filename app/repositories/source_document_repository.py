from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.domain.enums import SourceType
from app.models.source_document import SourceDocument


class SourceDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        return await self._session.get(SourceDocument, document_id)

    async def belongs_to_project(self, document_id: UUID, project_id: UUID) -> bool:
        doc = await self.get_by_id(document_id)
        return doc is not None and doc.project_id == project_id

    async def create(
        self,
        *,
        project_id: UUID,
        filename: str,
        original_path: str | None,
        mime_type: str | None,
        source_type: SourceType,
        raw_text: str | None,
        metadata_json: dict,
    ) -> SourceDocument:
        d = SourceDocument(
            project_id=project_id,
            filename=filename,
            original_path=original_path,
            mime_type=mime_type,
            source_type=source_type,
            raw_text=raw_text,
            metadata_json=metadata_json,
        )
        self._session.add(d)
        await self._session.flush()
        return d

    async def list_by_project(self, project_id: UUID) -> list[SourceDocument]:
        stmt = (
            select(SourceDocument)
            .options(
                load_only(
                    SourceDocument.id,
                    SourceDocument.project_id,
                    SourceDocument.filename,
                    SourceDocument.mime_type,
                    SourceDocument.source_type,
                    SourceDocument.created_at,
                )
            )
            .where(SourceDocument.project_id == project_id)
            .order_by(SourceDocument.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project_window(
        self,
        project_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> list[SourceDocument]:
        stmt = (
            select(SourceDocument)
            .options(
                load_only(
                    SourceDocument.id,
                    SourceDocument.project_id,
                    SourceDocument.filename,
                    SourceDocument.mime_type,
                    SourceDocument.source_type,
                    SourceDocument.created_at,
                )
            )
            .where(SourceDocument.project_id == project_id)
            .order_by(SourceDocument.created_at.desc(), SourceDocument.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: UUID) -> int:
        q = await self._session.scalar(
            select(func.count())
            .select_from(SourceDocument)
            .where(SourceDocument.project_id == project_id)
        )
        return int(q or 0)
