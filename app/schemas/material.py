from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MaterialType, ProcessingStatus


class MaterialBase(BaseModel):
    title: str | None = None
    source_uri: str | None = None
    mime_type: str | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class MaterialCreate(MaterialBase):
    material_type: MaterialType
    raw_text: str | None = None
    audio_filename: str | None = Field(
        default=None,
        description="Original filename hint when uploading audio (storage key set server-side).",
    )


class MaterialUpdate(BaseModel):
    title: str | None = None
    source_uri: str | None = None
    status: ProcessingStatus | None = None
    extra_metadata: dict[str, Any] | None = None


class MaterialRead(MaterialBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_type: MaterialType
    status: ProcessingStatus
    raw_text: str | None
    normalized_text: str | None
    audio_storage_key: str | None
    processing_error: str | None
    parent_material_id: UUID | None
    created_at: datetime
    updated_at: datetime
