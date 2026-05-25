from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_batch import ResearchBatch


class BatchPublicReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Opaque token → batch for read-only public report access."""

    __tablename__ = "batch_public_reports"
    __table_args__ = (UniqueConstraint("batch_id", name="uq_batch_public_reports_batch_id"),)

    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)

    batch: Mapped["ResearchBatch"] = relationship(
        "ResearchBatch",
        back_populates="public_report_link",
    )
