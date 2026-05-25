"""Interview units (logical interviews inside one document)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview_unit import InterviewUnit


async def count_units_for_documents(session: AsyncSession, document_ids: list[UUID]) -> int:
    if not document_ids:
        return 0
    q = await session.scalar(
        select(func.count()).select_from(InterviewUnit).where(InterviewUnit.source_document_id.in_(document_ids))
    )
    return int(q or 0)


async def list_units_for_documents(
    session: AsyncSession,
    document_ids: list[UUID],
    *,
    limit: int = 500,
) -> list[InterviewUnit]:
    if not document_ids:
        return []
    stmt = (
        select(InterviewUnit)
        .where(InterviewUnit.source_document_id.in_(document_ids))
        .order_by(InterviewUnit.source_document_id.asc(), InterviewUnit.unit_index.asc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def list_unit_id_strings_for_documents(session: AsyncSession, document_ids: list[UUID]) -> list[str]:
    rows = await list_units_for_documents(session, document_ids, limit=2000)
    return [str(u.id) for u in rows]
