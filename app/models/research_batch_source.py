import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.domain.enums import BatchSourceProcessingStatus
from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_batch import ResearchBatch
    from app.models.source_audio import SourceAudio
    from app.models.source_document import SourceDocument


class ResearchBatchSource(Base, UUIDPrimaryKeyMixin):
    """One document or one audio interview linked to a batch."""

    __tablename__ = "research_batch_sources"
    __table_args__ = (
        CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int = 1",
            name="ck_research_batch_sources_one_surface",
        ),
        Index("ix_research_batch_sources_batch_id", "batch_id"),
        Index("ix_research_batch_sources_batch_processing", "batch_id", "processing_status"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_audio_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_audios.id", ondelete="CASCADE"),
        nullable=True,
    )
    processing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=BatchSourceProcessingStatus.COMPLETED.value,
    )
    sort_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    batch: Mapped["ResearchBatch"] = relationship(back_populates="sources")
    source_document: Mapped["SourceDocument | None"] = relationship()
    source_audio: Mapped["SourceAudio | None"] = relationship()
