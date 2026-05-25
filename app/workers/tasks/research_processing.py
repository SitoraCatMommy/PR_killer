from __future__ import annotations

import logging
import struct
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.text_chunk import TextChunk
from app.services.processing_orchestrator_service import ProcessingOrchestratorService

logger = logging.getLogger(__name__)


def _document_chunk_advisory_ints(document_id: UUID) -> tuple[int, int]:
    b = document_id.bytes
    k1 = struct.unpack(">i", b[0:4])[0]
    k2 = struct.unpack(">i", b[4:8])[0]
    return k1, k2


def _try_pg_advisory_lock_chunk_doc(session: Session, document_id: UUID) -> bool:
    if session.get_bind().dialect.name != "postgresql":
        return True
    k1, k2 = _document_chunk_advisory_ints(document_id)
    got = session.execute(
        text("SELECT pg_try_advisory_lock(CAST(:k1 AS INTEGER), CAST(:k2 AS INTEGER))"),
        {"k1": k1, "k2": k2},
    ).scalar_one()
    return bool(got)


def _release_pg_advisory_lock_chunk_doc(session: Session, document_id: UUID) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    k1, k2 = _document_chunk_advisory_ints(document_id)
    session.execute(
        text("SELECT pg_advisory_unlock(CAST(:k1 AS INTEGER), CAST(:k2 AS INTEGER))"),
        {"k1": k1, "k2": k2},
    )


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
        if not _try_pg_advisory_lock_chunk_doc(session, did):
            return {
                "status": "already_processing",
                "source_document_id": source_document_id,
                "chunk_status": "already_processing",
            }
        try:
            existing = int(
                session.scalar(
                    select(func.count()).select_from(TextChunk).where(TextChunk.source_document_id == did)
                )
                or 0
            )
            if existing > 0:
                return {
                    "status": "ok",
                    "source_document_id": source_document_id,
                    "chunk_count": existing,
                    "chunking_strategy": st,
                    "chunk_status": "noop_already_chunked",
                    "skipped_chunk": True,
                }
            n = orch.chunk_source_document_sync(session, did, strategy=st)
        finally:
            _release_pg_advisory_lock_chunk_doc(session, did)
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
