from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AudioPipelineProgressRead(BaseModel):
    """GET /sources/audios/{id}/progress — background chunked transcription state."""

    source_audio_id: UUID | None = None
    filename: str = ""
    overall_status: str
    total_chunks: int = 0
    done_chunks: int = 0
    failed_chunks: int = 0
    current_stage: str
    last_error: str | None = None
    # UI: uploaded | splitting | transcribing | analyzing | done | failed
    pipeline_stage: str = ""
    progress_percent: int = Field(
        0, ge=0, le=100, description="Chunk-level completion 0..100; 100 when done"
    )


class BatchAudioPipelineItemRead(AudioPipelineProgressRead):
    """One audio row in a batch with identifiers for UI lists."""

    source_audio_id: UUID  # type: ignore[assignment]
    filename: str


class BatchAudioPipelineSummary(BaseModel):
    total_audios: int = 0
    ready: int = 0
    failed: int = 0
    in_progress: int = 0
    total_interviews: int = 0
    processed_interviews: int = 0
    errors_count: int = 0


class BatchAudioPipelineResponse(BaseModel):
    batch_id: UUID
    items: list[BatchAudioPipelineItemRead]
    summary: BatchAudioPipelineSummary
    meta: dict[str, Any] = Field(default_factory=dict)
