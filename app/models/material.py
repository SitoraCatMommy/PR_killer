import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import MaterialType, ProcessingStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.insight_source_link import InsightSourceLink
    from app.models.material_extracted_entity import MaterialExtractedEntity


class Material(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "materials"

    material_type: Mapped[MaterialType] = mapped_column(
        SAEnum(MaterialType, name="material_type", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status", native_enum=False, length=32),
        nullable=False,
        default=ProcessingStatus.PENDING,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    parent_material_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    extracted_entities: Mapped[list["MaterialExtractedEntity"]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
    )
    insight_links: Mapped[list["InsightSourceLink"]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
    )
