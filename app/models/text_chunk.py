import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.extracted_entity import ExtractedEntity
    from app.models.project import Project
    from app.models.source_audio import SourceAudio
    from app.models.source_document import SourceDocument
    from app.models.transcript import Transcript

# Align with migrations / embedding models (e.g. OpenAI text-embedding-3)
TEXT_CHUNK_EMBEDDING_DIMENSION = 1536


class TextChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "text_chunks"
    __table_args__ = (
        CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int + "
            "(transcript_id IS NOT NULL)::int = 1",
            name="ck_text_chunks_exactly_one_source",
        ),
        Index("ix_text_chunks_project_id_created_at", "project_id", "created_at"),
        Index("ix_text_chunks_transcript_id", "transcript_id"),
        Index("ix_text_chunks_source_document_id", "source_document_id"),
        Index("ix_text_chunks_source_audio_id", "source_audio_id"),
        Index(
            "uq_text_chunks_project_document_chunk_index",
            "project_id",
            "source_document_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("source_document_id IS NOT NULL"),
        ),
        Index(
            "uq_text_chunks_project_audio_chunk_index",
            "project_id",
            "source_audio_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("source_audio_id IS NOT NULL"),
        ),
        Index(
            "uq_text_chunks_transcript_chunk_index",
            "transcript_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("transcript_id IS NOT NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(TEXT_CHUNK_EMBEDDING_DIMENSION),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="text_chunks")
    source_document: Mapped["SourceDocument | None"] = relationship(back_populates="text_chunks")
    source_audio: Mapped["SourceAudio | None"] = relationship(back_populates="text_chunks")
    transcript: Mapped["Transcript | None"] = relationship(back_populates="text_chunks")
    extracted_entities: Mapped[list["ExtractedEntity"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )
