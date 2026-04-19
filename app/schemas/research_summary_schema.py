from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import SummaryStatus


class ResearchSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: SummaryStatus
    summary_text: str
    key_findings_json: list[Any] | dict[str, Any]
    facts_json: list[Any] | dict[str, Any]
    hypotheses_json: list[Any] | dict[str, Any]
    risks_json: list[Any] | dict[str, Any]
    opportunities_json: list[Any] | dict[str, Any]
    recommendations_json: list[Any] | dict[str, Any]
    open_questions_json: list[Any] | dict[str, Any]
    created_at: datetime
    updated_at: datetime
