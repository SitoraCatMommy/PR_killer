from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptPromoteRequest(BaseModel):
    """Create a text document from the latest completed transcript of this audio."""

    target_project_id: UUID = Field(description="Project that will own the new SourceDocument.")
    research_batch_id: UUID | None = Field(
        default=None,
        description="Optional batch in target_project to attach the new document to.",
    )
    filename_stem: str | None = Field(
        default=None,
        max_length=200,
        description="Base name without extension; defaults from audio filename.",
    )


class TranscriptPromoteResponse(BaseModel):
    source_document_id: UUID
    target_project_id: UUID
    research_batch_id: UUID | None = None
    transcript_id: UUID
