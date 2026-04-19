from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import JobStatus


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transcript_id: UUID
    speaker_label: str | None
    start_seconds: Decimal
    end_seconds: Decimal
    text: str
    confidence_score: float | None
    created_at: datetime


class TranscriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_audio_id: UUID
    full_text: str
    language: str | None
    status: JobStatus
    provider_name: str | None
    created_at: datetime
    updated_at: datetime
    extracted_entities_count: int = 0
