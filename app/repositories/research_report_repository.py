from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_report import ResearchReport


class ResearchReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_for_project(self, project_id: UUID) -> ResearchReport | None:
        stmt = (
            select(ResearchReport)
            .where(ResearchReport.project_id == project_id)
            .order_by(ResearchReport.updated_at.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def delete_all_for_project(self, project_id: UUID) -> None:
        await self._session.execute(delete(ResearchReport).where(ResearchReport.project_id == project_id))
