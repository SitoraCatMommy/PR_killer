"""Legacy material-linked entities (table `extracted_entities`)."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import EntityKind
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.material import Material


class MaterialExtractedEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_entities"
    __table_args__ = (
        UniqueConstraint("material_id", "fingerprint", name="uq_entity_material_fingerprint"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[EntityKind] = mapped_column(
        SAEnum(EntityKind, name="entity_kind", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    material: Mapped["Material"] = relationship(back_populates="extracted_entities")
