from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InsightSourceLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    span_start: int | None
    span_end: int | None
    quote: str | None
    locator: dict[str, Any]


class InsightCreate(BaseModel):
    headline: str = Field(max_length=512)
    summary: str | None = None
    body: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    dedup_key: str = Field(max_length=128)
    material_id: UUID
    span_start: int | None = None
    span_end: int | None = None
    quote: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str | None = None


class InsightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    headline: str
    summary: str | None
    body: str | None
    confidence: float | None
    dedup_key: str
    canonical_insight_id: UUID | None
    embedding_model: str | None
    created_at: datetime
    updated_at: datetime
    source_links: list[InsightSourceLinkRead] = Field(default_factory=list)
