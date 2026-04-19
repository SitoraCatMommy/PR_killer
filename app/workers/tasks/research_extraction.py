from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.models.extracted_entity import ExtractedEntity
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.transcript import Transcript
from app.services.research_extraction_service import ExtractionService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.research_extraction.extract_entities_for_document")
def extract_entities_for_document(source_document_id: str) -> dict:
    did = UUID(source_document_id)
    svc = ExtractionService()
    logger.info(
        "extract_entities_for_document: provider_class=%s",
        type(svc._provider).__qualname__,
    )
    try:
        with sync_session_scope() as session:
            n = svc.extract_for_document_sync(session, did)
            doc = session.get(SourceDocument, did)
            if doc is not None:
                total_proj = int(
                    session.scalar(
                        select(func.count()).select_from(ExtractedEntity).where(
                            ExtractedEntity.project_id == doc.project_id
                        )
                    )
                    or 0
                )
                logger.info(
                    "extract_entities_for_document: created=%s project_id=%s total_extracted_entities_in_project=%s",
                    n,
                    doc.project_id,
                    total_proj,
                )
        return {"status": "ok", "source_document_id": source_document_id, "entities_created": n}
    except ValueError as e:
        if str(e) == "source_document_not_found":
            logger.warning("extract_entities_for_document: document missing %s", source_document_id)
            return {"status": "missing", "source_document_id": source_document_id}
        raise


@celery_app.task(name="app.workers.tasks.research_extraction.extract_entities_for_transcript")
def extract_entities_for_transcript(transcript_id: str) -> dict:
    tid = UUID(transcript_id)
    svc = ExtractionService()
    logger.info(
        "extract_entities_for_transcript: provider_class=%s",
        type(svc._provider).__qualname__,
    )
    try:
        with sync_session_scope() as session:
            n = svc.extract_for_transcript_sync(session, tid)
            tr = session.get(Transcript, tid)
            if tr is not None:
                audio = session.get(SourceAudio, tr.source_audio_id)
                if audio is not None:
                    total_proj = int(
                        session.scalar(
                            select(func.count()).select_from(ExtractedEntity).where(
                                ExtractedEntity.project_id == audio.project_id
                            )
                        )
                        or 0
                    )
                    logger.info(
                        "extract_entities_for_transcript: created=%s project_id=%s total_extracted_entities_in_project=%s",
                        n,
                        audio.project_id,
                        total_proj,
                    )
        return {"status": "ok", "transcript_id": transcript_id, "entities_created": n}
    except ValueError as e:
        if str(e) == "transcript_not_found":
            logger.warning("extract_entities_for_transcript: transcript missing %s", transcript_id)
            return {"status": "missing", "transcript_id": transcript_id}
        raise


@celery_app.task(name="app.workers.tasks.research_extraction.extract_entities_for_audio")
def extract_entities_for_audio(source_audio_id: str) -> dict:
    aid = UUID(source_audio_id)
    svc = ExtractionService()
    logger.info(
        "extract_entities_for_audio: provider_class=%s",
        type(svc._provider).__qualname__,
    )
    try:
        with sync_session_scope() as session:
            n = svc.extract_for_audio_sync(session, aid)
            audio = session.get(SourceAudio, aid)
            if audio is not None:
                total_proj = int(
                    session.scalar(
                        select(func.count()).select_from(ExtractedEntity).where(
                            ExtractedEntity.project_id == audio.project_id
                        )
                    )
                    or 0
                )
                logger.info(
                    "extract_entities_for_audio: created=%s project_id=%s total_extracted_entities_in_project=%s",
                    n,
                    audio.project_id,
                    total_proj,
                )
        return {"status": "ok", "source_audio_id": source_audio_id, "entities_created": n}
    except ValueError as e:
        if str(e) == "source_audio_not_found":
            logger.warning("extract_entities_for_audio: audio missing %s", source_audio_id)
            return {"status": "missing", "source_audio_id": source_audio_id}
        raise
