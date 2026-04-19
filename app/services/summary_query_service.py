from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_repository import ProjectRepository
from app.repositories.research_summary_repository import ResearchSummaryRepository
from app.schemas.research_summary_schema import ResearchSummaryRead


class SummaryQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._summaries = ResearchSummaryRepository(session)
        self._projects = ProjectRepository(session)

    async def get_latest_for_project(self, project_id: UUID) -> ResearchSummaryRead | None:
        if not await self._projects.exists(project_id):
            raise ValueError("project_not_found")
        row = await self._summaries.get_latest_for_project(project_id)
        if row is None:
            return None
        return ResearchSummaryRead.model_validate(row)
