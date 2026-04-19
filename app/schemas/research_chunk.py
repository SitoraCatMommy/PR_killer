from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TextChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_document_id: UUID | None
    source_audio_id: UUID | None
    transcript_id: UUID | None
    chunk_index: int
    text: str
    token_count: int | None
    created_at: datetime
