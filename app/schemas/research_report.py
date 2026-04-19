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
