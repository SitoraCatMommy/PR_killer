from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SourceType
from app.schemas.pagination import PaginatedMeta
from app.schemas.research_transcript import TranscriptRead, TranscriptSegmentRead


class SourceDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    filename: str
    original_path: str | None
    mime_type: str | None
    source_type: SourceType
    raw_text: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class SourceAudioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    filename: str
    original_path: str | None
    mime_type: str | None
    duration_seconds: Decimal | None
    language: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class DocumentSourceListItem(BaseModel):
    source_kind: Literal["document"] = "document"
    id: UUID
    project_id: UUID
    filename: str
    mime_type: str | None
    source_type: SourceType
    created_at: datetime


class AudioSourceListItem(BaseModel):
    source_kind: Literal["audio"] = "audio"
    id: UUID
    project_id: UUID
    filename: str
    mime_type: str | None
    language: str | None
    created_at: datetime


class UnifiedSourcesResponse(BaseModel):
    items: list[DocumentSourceListItem | AudioSourceListItem]
    meta: PaginatedMeta


class SourceDocumentDetailRead(SourceDocumentRead):
    transcript: None = None
    transcript_segments_count: int = 0
    text_chunks_count: int = 0
    extracted_entities_count: int = 0


class SourceAudioDetailRead(SourceAudioRead):
    transcript: TranscriptRead | None = None
    transcript_segments_count: int = 0
    transcript_segments_sample: list[TranscriptSegmentRead] = Field(default_factory=list)
    text_chunks_count: int = 0
    extracted_entities_count: int = 0


class RawTextNoteCreate(BaseModel):
    title: str = Field(max_length=1024)
    text: str
    metadata_json: dict[str, Any] | None = None
