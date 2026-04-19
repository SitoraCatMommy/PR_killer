from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.infrastructure.database import DbSession
from app.infrastructure.settings import get_settings
from app.models.transcript import Transcript
from app.schemas.processing import ProcessingTaskQueued
from app.workers.tasks.research_extraction import extract_entities_for_transcript
from app.workers.tasks.research_processing import chunk_transcript

router = APIRouter(prefix="/transcripts", tags=["research-transcripts"])


@router.post(
    "/{transcript_id}/chunk",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_chunk_transcript(
    transcript_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    row = await session.get(Transcript, transcript_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "transcript_not_found", "message": "Transcript not found"},
        )
    task = chunk_transcript.delay(str(transcript_id), "fixed")
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.post(
    "/{transcript_id}/chunk/semantic",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_chunk_transcript_semantic(
    transcript_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    if not (get_settings().openai_api_key or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "openai_not_configured",
                "message": "Set OPENAI_API_KEY to use semantic (OpenAI) chunking.",
            },
        )
    row = await session.get(Transcript, transcript_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "transcript_not_found", "message": "Transcript not found"},
        )
    task = chunk_transcript.delay(str(transcript_id), "openai")
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.post(
    "/{transcript_id}/extract",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_extract_transcript(
    transcript_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    row = await session.get(Transcript, transcript_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "transcript_not_found", "message": "Transcript not found"},
        )
    task = extract_entities_for_transcript.delay(str(transcript_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")
