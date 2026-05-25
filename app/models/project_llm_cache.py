import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectLlmCache(Base, UUIDPrimaryKeyMixin):
    """Cached JSON payloads for expensive project-level LLM endpoints."""

    __tablename__ = "project_llm_cache"
    __table_args__ = (
        Index("ix_project_llm_cache_project_id", "project_id"),
        Index("ix_project_llm_cache_project_kind", "project_id", "cache_kind"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    cache_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(767), nullable=False, unique=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship()
