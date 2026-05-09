from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ReportStatus


class ResearchReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: ReportStatus
    title: str
    description: str | None
    executive_summary: str
    key_findings_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    problems_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    patterns_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    risks_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    hypotheses_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    recommendations_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    forecast_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    next_steps_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    external_articles_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    supporting_quotes_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    report_extras_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResearchReportEnvelope(BaseModel):
    report: ResearchReportRead | None = None


class PRAnalysisReadinessSource(BaseModel):
    source_kind: str
    source_id: UUID
    title: str | None = None
    processable: bool
    chunk_count: int
    entity_count: int
    pr_entity_count: int
    needs_chunking: bool
    needs_extraction: bool
    low_signal: bool
    reason: str | None = None


class PRAnalysisReadiness(BaseModel):
    ready_for_report: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_count: int
    processable_document_count: int
    completed_transcript_audio_count: int
    chunk_count: int
    entity_count: int
    pr_entity_count: int
    supporting_fact_count: int
    needs_chunking_count: int
    needs_extraction_count: int
    low_signal_source_count: int
    aggregation_exists: bool
    min_pr_entity_count: int
    sources: list[PRAnalysisReadinessSource] = Field(default_factory=list)
