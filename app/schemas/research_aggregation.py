from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ResearchAggregationSnapshotRead(BaseModel):
    project_id: UUID
    snapshot_type: str
    period_key: str
    payload_json: dict[str, Any]
    created_at: datetime


class ResearchAggregationSnapshotResponse(BaseModel):
    snapshot: ResearchAggregationSnapshotRead | None = Field(
        default=None,
        description="Null if aggregate has not been run for this project.",
    )
