from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source_audio import SourceAudio


class AudioSegment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Time slice of a source audio file for background transcription.

    ``transcript_text`` is per-slice ASR output during the pipeline; merged canonical text lives in
    ``Transcript.full_text``. See ``docs/transcript_storage.md``.
    """

    __tablename__ = "audio_segments"
    __table_args__ = (
        UniqueConstraint("source_audio_id", "segment_index", name="uq_audio_segments_audio_index"),
        Index("ix_audio_segments_source_audio_id", "source_audio_id"),
        Index("ix_audio_segments_status", "status"),
    )

    source_audio_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_audios.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_index: Mapped[int] = mapped_column(nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    segment_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(256), nullable=True)

    source_audio: Mapped["SourceAudio"] = relationship(back_populates="audio_segments")
