from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectPublicReportTokenRedirect(Base, UUIDPrimaryKeyMixin):
    """Legacy batch public tokens mapped to a project after migration."""

    __tablename__ = "project_public_report_token_redirects"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)

    project: Mapped["Project"] = relationship()
