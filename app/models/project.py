import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.aggregation_snapshot import AggregationSnapshot
    from app.models.extracted_entity import ExtractedEntity
    from app.models.research_report import ResearchReport
    from app.models.research_summary import ResearchSummary
    from app.models.source_audio import SourceAudio
    from app.models.source_document import SourceDocument
    from app.models.text_chunk import TextChunk


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    source_audios: Mapped[list["SourceAudio"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    text_chunks: Mapped[list["TextChunk"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    extracted_entities: Mapped[list["ExtractedEntity"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    aggregation_snapshots: Mapped[list["AggregationSnapshot"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    research_summaries: Mapped[list["ResearchSummary"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    research_reports: Mapped[list["ResearchReport"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
