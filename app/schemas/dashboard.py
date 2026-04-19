from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import DashboardAggregateKind


class DashboardAggregateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: DashboardAggregateKind
    period_key: str
    payload: dict[str, Any]
    computed_at: datetime
