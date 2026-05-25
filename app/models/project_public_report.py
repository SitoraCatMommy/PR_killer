from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectPublicReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Opaque token → project for read-only public report access."""

    __tablename__ = "project_public_reports"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_public_reports_project_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)

    project: Mapped["Project"] = relationship()
