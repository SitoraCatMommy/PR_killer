from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DashboardAggregateKind, ProcessingStatus
from app.models.material_extracted_entity import MaterialExtractedEntity
from app.models.insight import Insight
from app.models.material import Material
from app.repositories.dashboard_repository import DashboardRepository


class AggregationService:
    """Compute dashboard-ready aggregates stored for fast reads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._dashboard = DashboardRepository(session)

    def _period_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def recompute_all(self) -> None:
        period = self._period_key()

        m_total = await self._session.scalar(select(func.count()).select_from(Material)) or 0
        m_by_status = dict(
            (await self._session.execute(
                select(Material.status, func.count())
                .group_by(Material.status)
            )).all()
        )
        i_total = await self._session.scalar(select(func.count()).select_from(Insight)) or 0
        e_total = await self._session.scalar(select(func.count()).select_from(MaterialExtractedEntity)) or 0

        await self._dashboard.upsert_aggregate(
            DashboardAggregateKind.MATERIAL_COUNTS,
            period,
            {"total": int(m_total), "by_status": {k.value: int(v) for k, v in m_by_status.items()}},
        )
        await self._dashboard.upsert_aggregate(
            DashboardAggregateKind.INSIGHT_COUNTS,
            period,
            {"total": int(i_total)},
        )
        await self._dashboard.upsert_aggregate(
            DashboardAggregateKind.ENTITY_FREQUENCY,
            period,
            {"total_entities": int(e_total)},
        )

        failed = int(m_by_status.get(ProcessingStatus.FAILED, 0))
        await self._dashboard.upsert_aggregate(
            DashboardAggregateKind.PIPELINE_HEALTH,
            period,
            {
                "failed_materials": failed,
                "failure_rate": (failed / m_total) if m_total else 0.0,
            },
        )
