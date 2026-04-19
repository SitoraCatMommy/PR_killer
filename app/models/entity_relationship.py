import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import RelationshipType
from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.extracted_entity import ExtractedEntity


class EntityRelationship(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint("from_entity_id <> to_entity_id", name="ck_entity_relationships_no_self_loop"),
        Index("ix_entity_relationships_from_entity_id", "from_entity_id"),
        Index("ix_entity_relationships_to_entity_id", "to_entity_id"),
        Index("ix_entity_relationships_relationship_type", "relationship_type"),
    )

    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_extracted_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_extracted_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        SAEnum(RelationshipType, name="relationship_type", native_enum=False, length=32),
        nullable=False,
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    from_entity: Mapped["ExtractedEntity"] = relationship(
        back_populates="outgoing_relationships",
        foreign_keys=[from_entity_id],
    )
    to_entity: Mapped["ExtractedEntity"] = relationship(
        back_populates="incoming_relationships",
        foreign_keys=[to_entity_id],
    )
