import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.insight import Insight
    from app.models.material import Material


class InsightSourceLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insight_source_links"

    insight_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("insights.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    insight: Mapped["Insight"] = relationship(back_populates="source_links")
    material: Mapped["Material"] = relationship(back_populates="insight_links")
