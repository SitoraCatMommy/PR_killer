from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch_public_report import BatchPublicReport


def new_public_token() -> str:
    return secrets.token_urlsafe(32)


class BatchPublicReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token(self, token: str) -> BatchPublicReport | None:
        t = (token or "").strip()
        if not t or len(t) > 96:
            return None
        stmt = select(BatchPublicReport).where(BatchPublicReport.token == t)
        return await self._session.scalar(stmt)

    async def upsert_for_batch(self, batch_id: UUID, *, token: str | None = None) -> BatchPublicReport:
        tok = token or new_public_token()
        row = await self._session.scalar(
            select(BatchPublicReport).where(BatchPublicReport.batch_id == batch_id)
        )
        if row is None:
            row = BatchPublicReport(batch_id=batch_id, token=tok)
            self._session.add(row)
        else:
            row.token = tok
        await self._session.flush()
        return row
