import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DashboardAggregateKind
from app.models.dashboard_aggregate import DashboardAggregate


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_aggregate(
        self,
        kind: DashboardAggregateKind,
        period_key: str,
        payload: dict,
    ) -> DashboardAggregate:
        now = datetime.now(timezone.utc)
        insert_stmt = insert(DashboardAggregate).values(
            id=uuid.uuid4(),
            kind=kind,
            period_key=period_key,
            payload=payload,
            computed_at=now,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_dashboard_kind_period",
            set_={
                "payload": insert_stmt.excluded.payload,
                "computed_at": insert_stmt.excluded.computed_at,
            },
        ).returning(DashboardAggregate)
        result = await self._session.execute(upsert_stmt)
        row = result.scalar_one()
        await self._session.flush()
        return row

    async def list_all(self) -> list[DashboardAggregate]:
        stmt = select(DashboardAggregate).order_by(
            DashboardAggregate.kind,
            DashboardAggregate.period_key,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
