import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class AggregationSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "aggregation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "snapshot_type",
            "period_key",
            name="uq_aggregation_snapshots_project_type_period",
        ),
        Index("ix_aggregation_snapshots_project_id_created_at", "project_id", "created_at"),
        Index("ix_aggregation_snapshots_period_key", "period_key"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="aggregation_snapshots")
