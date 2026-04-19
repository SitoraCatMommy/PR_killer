from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_repository import ProjectRepository
from app.schemas.pagination import PaginatedMeta
from app.schemas.research_project import ProjectCreate, ProjectListResponse, ProjectRead


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)

    async def create(self, body: ProjectCreate) -> ProjectRead:
        if not body.name.strip():
            raise ValueError("invalid_name")
        p = await self._projects.create(name=body.name.strip(), description=body.description)
        await self._session.commit()
        await self._session.refresh(p)
        return ProjectRead.model_validate(p)

    async def list_paginated(self, *, offset: int, limit: int) -> ProjectListResponse:
        rows, total = await self._projects.list_paginated(offset=offset, limit=limit)
        return ProjectListResponse(
            items=[ProjectRead.model_validate(r) for r in rows],
            meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        )

    async def get(self, project_id: UUID) -> ProjectRead | None:
        p = await self._projects.get_by_id(project_id)
        if p is None:
            return None
        return ProjectRead.model_validate(p)

    async def require(self, project_id: UUID) -> ProjectRead:
        p = await self.get(project_id)
        if p is None:
            raise ValueError("project_not_found")
        return p

    async def delete(self, project_id: UUID) -> bool:
        """Удалить проект и связанные данные (каскад по ORM). Возвращает False, если проекта нет."""
        ok = await self._projects.delete(project_id)
        if not ok:
            return False
        await self._session.commit()
        return True
