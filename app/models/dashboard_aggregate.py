import uuid
from typing import Any

from sqlalchemy import DateTime, Enum as SAEnum, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import DashboardAggregateKind
from app.models.base import Base, UUIDPrimaryKeyMixin


class DashboardAggregate(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "dashboard_aggregates"
    __table_args__ = (
        UniqueConstraint("kind", "period_key", name="uq_dashboard_kind_period"),
    )

    kind: Mapped[DashboardAggregateKind] = mapped_column(
        SAEnum(DashboardAggregateKind, name="dashboard_aggregate_kind", native_enum=False, length=64),
        nullable=False,
        index=True,
    )
    period_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
