from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntityType
from app.models.extracted_entity import ExtractedEntity
from app.models.transcript import Transcript


def stmt_delete_extracted_entities_for_document(source_document_id: UUID):
    return delete(ExtractedEntity).where(ExtractedEntity.source_document_id == source_document_id)


def stmt_delete_extracted_entities_for_transcript(transcript_id: UUID):
    return delete(ExtractedEntity).where(ExtractedEntity.transcript_id == transcript_id)


def stmt_delete_extracted_entities_for_audio_scope(source_audio_id: UUID):
    t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
    return delete(ExtractedEntity).where(
        or_(
            ExtractedEntity.source_audio_id == source_audio_id,
            ExtractedEntity.transcript_id.in_(t_sub),
        )
    )


class ExtractedEntityRepository:
    """Domain `research_extracted_entities` (not legacy material entities)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_for_document(self, source_document_id: UUID) -> int:
        q = await self._session.scalar(
            select(func.count())
            .select_from(ExtractedEntity)
            .where(ExtractedEntity.source_document_id == source_document_id)
        )
        return int(q or 0)

    async def count_for_audio(self, source_audio_id: UUID) -> int:
        t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
        q = await self._session.scalar(
            select(func.count())
            .select_from(ExtractedEntity)
            .where(
                or_(
                    ExtractedEntity.source_audio_id == source_audio_id,
                    ExtractedEntity.transcript_id.in_(t_sub),
                )
            )
        )
        return int(q or 0)

    async def count_for_transcript(self, transcript_id: UUID) -> int:
        q = await self._session.scalar(
            select(func.count())
            .select_from(ExtractedEntity)
            .where(ExtractedEntity.transcript_id == transcript_id)
        )
        return int(q or 0)

    async def delete_for_source_document(self, source_document_id: UUID) -> None:
        await self._session.execute(stmt_delete_extracted_entities_for_document(source_document_id))

    async def delete_for_transcript(self, transcript_id: UUID) -> None:
        await self._session.execute(stmt_delete_extracted_entities_for_transcript(transcript_id))

    async def delete_for_audio_scope(self, source_audio_id: UUID) -> None:
        await self._session.execute(stmt_delete_extracted_entities_for_audio_scope(source_audio_id))

    async def list_for_project(
        self,
        project_id: UUID,
        *,
        entity_type: EntityType | None,
        min_confidence: float | None,
        source_document_id: UUID | None,
        source_audio_id: UUID | None,
        transcript_id: UUID | None,
        offset: int,
        limit: int,
        exclude_entity_types: frozenset[EntityType] | None = None,
    ) -> tuple[list[ExtractedEntity], int]:
        stmt = select(ExtractedEntity).where(ExtractedEntity.project_id == project_id)
        count_stmt = select(func.count()).select_from(ExtractedEntity).where(
            ExtractedEntity.project_id == project_id
        )
        if entity_type is not None:
            stmt = stmt.where(ExtractedEntity.entity_type == entity_type)
            count_stmt = count_stmt.where(ExtractedEntity.entity_type == entity_type)
        elif exclude_entity_types:
            ex = tuple(exclude_entity_types)
            if ex:
                stmt = stmt.where(~ExtractedEntity.entity_type.in_(ex))
                count_stmt = count_stmt.where(~ExtractedEntity.entity_type.in_(ex))
        if min_confidence is not None:
            stmt = stmt.where(ExtractedEntity.confidence_score >= min_confidence)
            count_stmt = count_stmt.where(ExtractedEntity.confidence_score >= min_confidence)
        if source_document_id is not None:
            stmt = stmt.where(ExtractedEntity.source_document_id == source_document_id)
            count_stmt = count_stmt.where(ExtractedEntity.source_document_id == source_document_id)
        if source_audio_id is not None:
            stmt = stmt.where(ExtractedEntity.source_audio_id == source_audio_id)
            count_stmt = count_stmt.where(ExtractedEntity.source_audio_id == source_audio_id)
        if transcript_id is not None:
            stmt = stmt.where(ExtractedEntity.transcript_id == transcript_id)
            count_stmt = count_stmt.where(ExtractedEntity.transcript_id == transcript_id)

        total = int(await self._session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(ExtractedEntity.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total
