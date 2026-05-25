from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_public_report import ProjectPublicReport
from app.models.project_public_report_token_redirect import ProjectPublicReportTokenRedirect


def new_public_token() -> str:
    return secrets.token_urlsafe(32)


class ProjectPublicReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token(self, token: str) -> ProjectPublicReport | None:
        t = (token or "").strip()
        if not t or len(t) > 96:
            return None
        row = await self._session.scalar(select(ProjectPublicReport).where(ProjectPublicReport.token == t))
        if row is not None:
            return row
        redirect = await self._session.scalar(
            select(ProjectPublicReportTokenRedirect).where(ProjectPublicReportTokenRedirect.token == t)
        )
        if redirect is None:
            return None
        return await self._session.scalar(
            select(ProjectPublicReport).where(ProjectPublicReport.project_id == redirect.project_id)
        )

    async def resolve_project_id(self, token: str) -> UUID | None:
        row = await self.get_by_token(token)
        return row.project_id if row is not None else None

    async def upsert_for_project(self, project_id: UUID, *, token: str | None = None) -> ProjectPublicReport:
        tok = token or new_public_token()
        row = await self._session.scalar(
            select(ProjectPublicReport).where(ProjectPublicReport.project_id == project_id)
        )
        if row is None:
            row = ProjectPublicReport(project_id=project_id, token=tok)
            self._session.add(row)
        else:
            row.token = tok
        await self._session.flush()
        return row

    async def register_redirect_token(self, project_id: UUID, token: str) -> None:
        t = (token or "").strip()
        if not t:
            return
        existing = await self._session.scalar(
            select(ProjectPublicReportTokenRedirect).where(ProjectPublicReportTokenRedirect.token == t)
        )
        if existing is not None:
            existing.project_id = project_id
        else:
            self._session.add(ProjectPublicReportTokenRedirect(project_id=project_id, token=t))
        await self._session.flush()
