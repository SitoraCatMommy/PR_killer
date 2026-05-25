from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.batch_public_report import BatchPublicReport
    from app.models.project import Project
    from app.models.research_batch_llm_cache import ResearchBatchLlmCache
    from app.models.research_batch_source import ResearchBatchSource
    from app.models.research_report import ResearchReport


class ResearchBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Multi-source research study within one project (subset of interviews / documents)."""

    __tablename__ = "research_batches"
    __table_args__ = (Index("ix_research_batches_project_id_created_at", "project_id", "created_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When set, batch-scoped LLM/export uses this code; else project.output_language.
    output_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    single_file_multi_interview_mode: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    project: Mapped["Project"] = relationship(back_populates="research_batches")
    sources: Mapped[list["ResearchBatchSource"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    research_reports: Mapped[list["ResearchReport"]] = relationship(
        back_populates="batch",
        foreign_keys="ResearchReport.batch_id",
    )
    llm_caches: Mapped[list["ResearchBatchLlmCache"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    public_report_link: Mapped["BatchPublicReport | None"] = relationship(
        "BatchPublicReport",
        back_populates="batch",
        cascade="all, delete-orphan",
        uselist=False,
    )
