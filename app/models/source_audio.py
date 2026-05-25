import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import SourceProcessingStatus
from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.audio_segment import AudioSegment
    from app.models.project import Project
    from app.models.text_chunk import TextChunk
    from app.models.transcript import Transcript


class SourceAudio(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "source_audios"
    __table_args__ = (
        Index("ix_source_audios_project_id_created_at", "project_id", "created_at"),
        Index("ix_source_audios_project_processing", "project_id", "processing_status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    audio_pipeline_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", index=True)
    audio_pipeline_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_file_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceProcessingStatus.IDLE.value,
        index=True,
    )
    processing_sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="source_audios")
    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="source_audio",
        cascade="all, delete-orphan",
    )
    text_chunks: Mapped[list["TextChunk"]] = relationship(
        back_populates="source_audio",
        cascade="all, delete-orphan",
    )
    audio_segments: Mapped[list["AudioSegment"]] = relationship(
        back_populates="source_audio",
        cascade="all, delete-orphan",
    )
