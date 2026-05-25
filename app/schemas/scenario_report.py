"""Ready-to-use batch report modes (packaging existing analytics)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.decision_layer import PriorityActionItem
from app.schemas.research_batch import AudiencePortraitFields

ReportMode = Literal["pr_audit", "audience", "messaging"]


class PRAuditScenarioSection(BaseModel):
    brand_perception_summary: str = ""
    risks: list[str] = Field(default_factory=list)
    communication_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    priority_actions: list[PriorityActionItem] = Field(default_factory=list)


class AudienceInsightScenarioSection(BaseModel):
    portrait: AudiencePortraitFields
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    interview_count: int = 0
    audience_snapshot: dict[str, Any] = Field(default_factory=dict)
    top_patterns: list[dict[str, Any]] = Field(default_factory=list)
    word_frequency: list[dict[str, Any]] = Field(default_factory=list)


class MessagingKitScenarioSection(BaseModel):
    talking_points: list[str] = Field(default_factory=list)
    recommended_messages: list[str] = Field(default_factory=list)
    audience_phrases: list[str] = Field(default_factory=list)
    media_hooks: list[str] = Field(default_factory=list)


class BatchScenarioReportResponse(BaseModel):
    mode: ReportMode
    batch_id: UUID
    meta: dict[str, Any] = Field(default_factory=dict)
    pr_audit: PRAuditScenarioSection | None = None
    audience_insight: AudienceInsightScenarioSection | None = None
    messaging_kit: MessagingKitScenarioSection | None = None
