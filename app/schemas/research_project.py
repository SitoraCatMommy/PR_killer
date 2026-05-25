from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pagination import PaginatedMeta


class ProjectCreate(BaseModel):
    name: str = Field(max_length=512)
    description: str | None = None
    output_language: str | None = Field(
        default=None,
        description="ru|uz|en — defaults to ru when omitted",
        max_length=8,
    )


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    output_language: str = "ru"
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectRead]
    meta: PaginatedMeta


class ProjectProcessingQueueItem(BaseModel):
    kind: str
    id: str
    filename: str = ""
    processing_status: str = "idle"
    processing_last_error: str | None = None


class ProjectProcessingQueueResponse(BaseModel):
    idle: int = 0
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    currently_processing: list[dict[str, str]] = Field(default_factory=list)
    sources: list[ProjectProcessingQueueItem] = Field(default_factory=list)
