import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Enum as SAEnum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import EntityType
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.entity_relationship import EntityRelationship

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.source_audio import SourceAudio
    from app.models.source_document import SourceDocument
    from app.models.text_chunk import TextChunk
    from app.models.transcript import Transcript


class ExtractedEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Domain extracted entity; always tied to a `TextChunk` and exactly one source surface."""

    __tablename__ = "research_extracted_entities"
    __table_args__ = (
        CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int + "
            "(transcript_id IS NOT NULL)::int = 1",
            name="ck_research_entities_exactly_one_source",
        ),
        Index("ix_research_entities_project_id_entity_type", "project_id", "entity_type"),
        Index("ix_research_entities_chunk_id", "chunk_id"),
        Index("ix_research_entities_project_id_created_at", "project_id", "created_at"),
        Index("ix_research_entities_canonical_entity_id", "canonical_entity_id"),
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
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("text_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(
            EntityType,
            name="entity_type",
            native_enum=False,
            length=32,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tags_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_extracted_entities.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped["Project"] = relationship(back_populates="extracted_entities")
    source_document: Mapped["SourceDocument | None"] = relationship()
    source_audio: Mapped["SourceAudio | None"] = relationship()
    transcript: Mapped["Transcript | None"] = relationship()
    chunk: Mapped["TextChunk"] = relationship(back_populates="extracted_entities")

    canonical_entity: Mapped["ExtractedEntity | None"] = relationship(
        remote_side="ExtractedEntity.id",
        foreign_keys="ExtractedEntity.canonical_entity_id",
        back_populates="non_canonical_duplicates",
    )
    non_canonical_duplicates: Mapped[list["ExtractedEntity"]] = relationship(
        back_populates="canonical_entity",
        foreign_keys="ExtractedEntity.canonical_entity_id",
    )

    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="from_entity",
        foreign_keys=[EntityRelationship.from_entity_id],
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="to_entity",
        foreign_keys=[EntityRelationship.to_entity_id],
        cascade="all, delete-orphan",
    )
