from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment


class TranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, transcript_id: UUID) -> Transcript | None:
        return await self._session.get(Transcript, transcript_id)

    async def get_latest_for_audio(self, source_audio_id: UUID) -> Transcript | None:
        stmt = (
            select(Transcript)
            .where(Transcript.source_audio_id == source_audio_id)
            .order_by(Transcript.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_segments(self, transcript_id: UUID) -> Transcript | None:
        stmt = (
            select(Transcript)
            .where(Transcript.id == transcript_id)
            .options(selectinload(Transcript.segments))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_segments(self, transcript_id: UUID) -> int:
        from sqlalchemy import func

        q = await self._session.scalar(
            select(func.count())
            .select_from(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
        )
        return int(q or 0)

    async def list_segments_preview(self, transcript_id: UUID, *, limit: int = 20) -> list[TranscriptSegment]:
        stmt = (
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.start_seconds)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
