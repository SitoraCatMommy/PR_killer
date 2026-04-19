from __future__ import annotations

import logging
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.services.processing_orchestrator_service import ProcessingOrchestratorService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.research_processing.transcribe_audio_source")
def transcribe_audio_source(source_audio_id: str) -> dict:
    sid = UUID(source_audio_id)
    orch = ProcessingOrchestratorService()
    with sync_session_scope() as session:
        tid = orch.transcribe_audio_source_sync(session, sid)
        chunk_count = orch.chunk_transcript_sync(session, tid, strategy="fixed")
    logger.info(
        "transcribe_audio_source: source_audio_id=%s transcript_id=%s chunk_count=%s",
        source_audio_id,
        tid,
        chunk_count,
    )
    return {
        "status": "ok",
        "source_audio_id": source_audio_id,
        "transcript_id": str(tid),
        "chunk_count": chunk_count,
    }


@celery_app.task(name="app.workers.tasks.research_processing.chunk_source_document")
def chunk_source_document(source_document_id: str, strategy: str = "fixed") -> dict:
    did = UUID(source_document_id)
    st = "openai" if strategy == "openai" else "fixed"
    if st == "openai" and not (get_settings().openai_api_key or "").strip():
        return {
            "status": "error",
            "code": "openai_not_configured",
            "source_document_id": source_document_id,
        }
    orch = ProcessingOrchestratorService()
    with sync_session_scope() as session:
        n = orch.chunk_source_document_sync(session, did, strategy=st)
    return {
        "status": "ok",
        "source_document_id": source_document_id,
        "chunk_count": n,
        "chunking_strategy": st,
    }


@celery_app.task(name="app.workers.tasks.research_processing.chunk_transcript")
def chunk_transcript(transcript_id: str, strategy: str = "fixed") -> dict:
    tid = UUID(transcript_id)
    st = "openai" if strategy == "openai" else "fixed"
    if st == "openai" and not (get_settings().openai_api_key or "").strip():
        return {
            "status": "error",
            "code": "openai_not_configured",
            "transcript_id": transcript_id,
        }
    orch = ProcessingOrchestratorService()
    with sync_session_scope() as session:
        n = orch.chunk_transcript_sync(session, tid, strategy=st)
    return {
        "status": "ok",
        "transcript_id": transcript_id,
        "chunk_count": n,
        "chunking_strategy": st,
    }
