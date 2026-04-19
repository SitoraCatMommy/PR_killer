"""Structured output from research entity extraction providers (before ORM persist)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import EntityType


class ExtractedEntityCandidate(BaseModel):
    """One proposed entity from a provider; maps to `ExtractedEntity` ORM."""

    entity_type: EntityType
    title: str = Field(max_length=512)
    content: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    tags_json: dict[str, Any] = Field(default_factory=dict)
    evidence_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        s = (v or "").strip()
        return s[:512] if s else "Untitled"


class ChunkExtractionBatch(BaseModel):
    """Provider response for one chunk (wrapper for validation / future metadata)."""

    entities: list[ExtractedEntityCandidate] = Field(default_factory=list)
