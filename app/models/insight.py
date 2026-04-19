import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SAEnum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.insight_source_link import InsightSourceLink

# Keep in sync with Alembic migration and settings default EMBEDDING_DIMENSION
INSIGHT_EMBEDDING_DIMENSION = 1536


class Insight(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "insights"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_insights_dedup_key"),)

    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    canonical_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("insights.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(INSIGHT_EMBEDDING_DIMENSION),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_links: Mapped[list["InsightSourceLink"]] = relationship(
        back_populates="insight",
        cascade="all, delete-orphan",
    )
