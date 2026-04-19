from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript


def stmt_chunks_for_document_ordered(source_document_id: UUID):
    return (
        select(TextChunk)
        .where(TextChunk.source_document_id == source_document_id)
        .order_by(TextChunk.chunk_index.asc(), TextChunk.id.asc())
    )


def stmt_chunks_for_transcript_ordered(transcript_id: UUID):
    return (
        select(TextChunk)
        .where(TextChunk.transcript_id == transcript_id)
        .order_by(TextChunk.chunk_index.asc(), TextChunk.id.asc())
    )


def stmt_chunks_for_audio_scope_ordered(source_audio_id: UUID):
    t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
    return (
        select(TextChunk)
        .where(
            or_(
                TextChunk.source_audio_id == source_audio_id,
                TextChunk.transcript_id.in_(t_sub),
            )
        )
        .order_by(TextChunk.chunk_index.asc(), TextChunk.id.asc())
    )


class TextChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_for_document(self, source_document_id: UUID) -> int:
        q = await self._session.scalar(
            select(func.count())
            .select_from(TextChunk)
            .where(TextChunk.source_document_id == source_document_id)
        )
        return int(q or 0)

    async def list_for_document_ordered(self, source_document_id: UUID) -> list[TextChunk]:
        result = await self._session.execute(stmt_chunks_for_document_ordered(source_document_id))
        return list(result.scalars().all())

    async def list_for_transcript_ordered(self, transcript_id: UUID) -> list[TextChunk]:
        result = await self._session.execute(stmt_chunks_for_transcript_ordered(transcript_id))
        return list(result.scalars().all())

    async def list_for_audio_scope_ordered(self, source_audio_id: UUID) -> list[TextChunk]:
        result = await self._session.execute(stmt_chunks_for_audio_scope_ordered(source_audio_id))
        return list(result.scalars().all())

    async def count_for_audio(self, source_audio_id: UUID) -> int:
        t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
        q = await self._session.scalar(
            select(func.count())
            .select_from(TextChunk)
            .where(
                or_(
                    TextChunk.source_audio_id == source_audio_id,
                    TextChunk.transcript_id.in_(t_sub),
                )
            )
        )
        return int(q or 0)
