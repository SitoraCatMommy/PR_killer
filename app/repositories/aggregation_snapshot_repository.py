from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.research_constants import PERIOD_KEY_ALL_TIME, SNAPSHOT_TYPE_RESEARCH_ENTITIES
from app.models.aggregation_snapshot import AggregationSnapshot


class AggregationSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_research_entity_snapshot(
        self,
        project_id: UUID,
    ) -> AggregationSnapshot | None:
        stmt = (
            select(AggregationSnapshot)
            .where(
                AggregationSnapshot.project_id == project_id,
                AggregationSnapshot.snapshot_type == SNAPSHOT_TYPE_RESEARCH_ENTITIES,
                AggregationSnapshot.period_key == PERIOD_KEY_ALL_TIME,
            )
            .order_by(AggregationSnapshot.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
