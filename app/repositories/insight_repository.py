from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.insight import Insight
from app.models.insight_source_link import InsightSourceLink


class InsightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_dedup_key(self, dedup_key: str) -> Insight | None:
        stmt = select(Insight).where(Insight.dedup_key == dedup_key).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_with_source(
        self,
        *,
        headline: str,
        summary: str | None,
        body: str | None,
        confidence: float | None,
        dedup_key: str,
        material_id: UUID,
        span_start: int | None,
        span_end: int | None,
        quote: str | None,
        locator: dict,
        embedding: list[float] | None,
        embedding_model: str | None,
        canonical_insight_id: UUID | None = None,
    ) -> Insight:
        insight = Insight(
            headline=headline,
            summary=summary,
            body=body,
            confidence=confidence,
            dedup_key=dedup_key,
            canonical_insight_id=canonical_insight_id,
            embedding=embedding,
            embedding_model=embedding_model,
        )
        link = InsightSourceLink(
            insight=insight,
            material_id=material_id,
            span_start=span_start,
            span_end=span_end,
            quote=quote,
            locator=locator,
        )
        self._session.add(insight)
        self._session.add(link)
        await self._session.flush()
        return insight

    async def list_with_links(self, limit: int = 100) -> list[Insight]:
        stmt = (
            select(Insight)
            .options(selectinload(Insight.source_links))
            .order_by(Insight.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())
