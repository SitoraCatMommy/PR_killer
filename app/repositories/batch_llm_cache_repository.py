from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_batch_llm_cache import ResearchBatchLlmCache


class BatchLlmCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_cache_key(self, cache_key: str) -> ResearchBatchLlmCache | None:
        stmt = select(ResearchBatchLlmCache).where(ResearchBatchLlmCache.cache_key == cache_key).limit(1)
        return await self._session.scalar(stmt)

    async def upsert_payload(
        self,
        *,
        batch_id: UUID,
        cache_kind: str,
        cache_key: str,
        payload_json: dict,
    ) -> ResearchBatchLlmCache:
        row = await self.get_by_cache_key(cache_key)
        if row is None:
            row = ResearchBatchLlmCache(
                batch_id=batch_id,
                cache_kind=cache_kind,
                cache_key=cache_key,
                payload_json=payload_json,
            )
            self._session.add(row)
        else:
            row.payload_json = payload_json
            row.cache_kind = cache_kind
            row.batch_id = batch_id
        await self._session.flush()
        return row

    async def delete_for_batch(self, batch_id: UUID) -> None:
        await self._session.execute(delete(ResearchBatchLlmCache).where(ResearchBatchLlmCache.batch_id == batch_id))
        await self._session.flush()
