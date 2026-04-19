import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ReportStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ResearchReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Structured AI research report for a project (Russian-facing content in JSON fields)."""

    __tablename__ = "research_reports"
    __table_args__ = (
        Index("ix_research_reports_project_id_updated_at", "project_id", "updated_at"),
        Index("ix_research_reports_project_id_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(
            ReportStatus,
            name="report_status",
            native_enum=False,
            length=32,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ReportStatus.DRAFT,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    key_findings_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    problems_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    patterns_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    risks_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    hypotheses_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    recommendations_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    forecast_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    next_steps_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    external_articles_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    supporting_quotes_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    report_extras_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=dict
    )

    project: Mapped["Project"] = relationship(back_populates="research_reports")
