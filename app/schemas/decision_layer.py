"""Decision layer: priority actions, impact/effort matrix, alerts (PR + research signals)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PriorityActionItem(BaseModel):
    action: str = ""
    impact: str = "medium"
    effort: str = "medium"
    reason: str = ""
    based_on: list[str] = Field(
        default_factory=list,
        description="EvidenceDrivenInsight.insight_id values this action is grounded on.",
    )

    @field_validator("impact", "effort", mode="before")
    @classmethod
    def _level(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        if s in ("high", "medium", "low"):
            return s
        return "medium"


class ImpactEffortMatrixItem(BaseModel):
    action: str = ""
    impact: str = "medium"
    effort: str = "medium"

    @field_validator("impact", "effort", mode="before")
    @classmethod
    def _level(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        if s in ("high", "medium", "low"):
            return s
        return "medium"


class DecisionAlertItem(BaseModel):
    type: str = "risk"
    message: str = ""
    severity: str = "medium"

    @field_validator("type", mode="before")
    @classmethod
    def _atype(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        if s in ("risk", "sentiment", "trust"):
            return s
        return "risk"

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        if s in ("high", "medium"):
            return s
        return "medium"
