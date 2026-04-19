import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.insight_repository import InsightRepository


class DeduplicationService:
    """Content-hash and repository-backed deduplication for insights."""

    def __init__(self, session: AsyncSession) -> None:
        self._insights = InsightRepository(session)

    @staticmethod
    def insight_dedup_key(
        *,
        headline: str,
        summary: str | None,
        material_id: UUID,
        locator: dict[str, Any],
    ) -> str:
        raw = f"{headline}|{summary or ''}|{material_id}|{sorted(locator.items())}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    async def find_canonical(self, dedup_key: str):
        return await self._insights.get_by_dedup_key(dedup_key)
