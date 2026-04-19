from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_summary import ResearchSummary


class ResearchSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_for_project(self, project_id: UUID) -> ResearchSummary | None:
        stmt = (
            select(ResearchSummary)
            .where(ResearchSummary.project_id == project_id)
            .order_by(ResearchSummary.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
