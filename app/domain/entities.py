from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.enums import (
    DashboardAggregateKind,
    EntityKind,
    MaterialType,
    ProcessingStatus,
)


@dataclass(slots=True)
class MaterialEntity:
    id: UUID
    material_type: MaterialType
    title: str | None
    source_uri: str | None
    status: ProcessingStatus
    raw_text: str | None
    normalized_text: str | None
    created_at: datetime
    updated_at: datetime
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InsightEntity:
    id: UUID
    headline: str
    summary: str | None
    body: str | None
    confidence: float | None
    dedup_key: str
    canonical_insight_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ExtractedEntityRecord:
    id: UUID
    material_id: UUID
    kind: EntityKind
    label: str
    normalized_value: str | None
    span_start: int | None
    span_end: int | None
    payload: dict[str, Any]
    fingerprint: str


@dataclass(slots=True)
class DashboardAggregateRecord:
    id: UUID
    kind: DashboardAggregateKind
    period_key: str
    payload: dict[str, Any]
    computed_at: datetime
