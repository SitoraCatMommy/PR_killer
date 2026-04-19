from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, project_id: UUID) -> bool:
        return (
            await self._session.scalar(select(Project.id).where(Project.id == project_id)) is not None
        )

    async def get_by_id(self, project_id: UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def create(self, *, name: str, description: str | None) -> Project:
        p = Project(name=name, description=description)
        self._session.add(p)
        await self._session.flush()
        return p

    async def list_paginated(self, *, offset: int, limit: int) -> tuple[list[Project], int]:
        count_stmt = select(func.count()).select_from(Project)
        total = int(await self._session.scalar(count_stmt) or 0)
        stmt = (
            select(Project)
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete(self, project_id: UUID) -> bool:
        p = await self._session.get(Project, project_id)
        if p is None:
            return False
        await self._session.delete(p)
        await self._session.flush()
        return True
