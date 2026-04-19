from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import EntityType
from app.schemas.pagination import PaginatedMeta


class ExtractedEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_document_id: UUID | None
    source_audio_id: UUID | None
    transcript_id: UUID | None
    chunk_id: UUID
    entity_type: EntityType
    title: str
    content: str
    confidence_score: float | None
    tags_json: dict[str, Any] | list[Any]
    evidence_json: dict[str, Any] | list[Any]
    canonical_entity_id: UUID | None
    created_at: datetime
    updated_at: datetime
    pr_implication: str = ""
    messaging_guidance: str = ""


class EntityListFilters(BaseModel):
    entity_type: EntityType | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_document_id: UUID | None = None
    source_audio_id: UUID | None = None
    transcript_id: UUID | None = None


class EntityListResponse(BaseModel):
    items: list[ExtractedEntityRead]
    meta: PaginatedMeta
