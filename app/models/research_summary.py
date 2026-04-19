import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import SummaryStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ResearchSummary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "research_summaries"
    __table_args__ = (
        Index("ix_research_summaries_project_id_status", "project_id", "status"),
        Index("ix_research_summaries_project_id_updated_at", "project_id", "updated_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[SummaryStatus] = mapped_column(
        SAEnum(
            SummaryStatus,
            name="summary_status",
            native_enum=False,
            length=32,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=SummaryStatus.DRAFT,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_findings_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    facts_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    hypotheses_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    risks_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    opportunities_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    recommendations_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )
    open_questions_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, insert_default=list
    )

    project: Mapped["Project"] = relationship(back_populates="research_summaries")
