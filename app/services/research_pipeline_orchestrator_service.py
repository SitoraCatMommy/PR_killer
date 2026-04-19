"""Project-level pipeline: ensure chunking + extraction + aggregation before downstream steps."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus
from app.models.extracted_entity import ExtractedEntity
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.services.processing_orchestrator_service import ProcessingOrchestratorService
from app.services.research_project_aggregation_service import ResearchAggregationService
from app.services.research_extraction_service import ExtractionService

logger = logging.getLogger(__name__)


def _count_document_chunks(session: Session, source_document_id: UUID) -> int:
    q = session.scalar(
        select(func.count()).select_from(TextChunk).where(TextChunk.source_document_id == source_document_id)
    )
    return int(q or 0)


def _count_document_entities(session: Session, source_document_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(ExtractedEntity.source_document_id == source_document_id)
    )
    return int(q or 0)


def _count_audio_scope_chunks(session: Session, source_audio_id: UUID) -> int:
    t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
    q = session.scalar(
        select(func.count())
        .select_from(TextChunk)
        .where(
            or_(
                TextChunk.source_audio_id == source_audio_id,
                TextChunk.transcript_id.in_(t_sub),
            )
        )
    )
    return int(q or 0)


def _count_audio_scope_entities(session: Session, source_audio_id: UUID) -> int:
    t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(
            or_(
                ExtractedEntity.source_audio_id == source_audio_id,
                ExtractedEntity.transcript_id.in_(t_sub),
            )
        )
    )
    return int(q or 0)


def _latest_completed_transcript(session: Session, source_audio_id: UUID) -> Transcript | None:
    tr = session.scalar(
        select(Transcript)
        .where(
            Transcript.source_audio_id == source_audio_id,
            Transcript.status == JobStatus.COMPLETED,
        )
        .order_by(Transcript.created_at.desc())
        .limit(1)
    )
    return tr


class ResearchPipelineOrchestratorService:
    """Uses existing sync services; no duplicated chunk/extract/aggregate logic."""

    def __init__(self) -> None:
        self._processing = ProcessingOrchestratorService()
        self._extraction = ExtractionService()
        self._aggregation = ResearchAggregationService()

    def ensure_project_sources_pipeline_sync(self, session: Session, project_id: UUID) -> dict[str, Any]:
        """Chunk (if needed) and extract (if no entities) for every text/audio source with data."""
        out: dict[str, Any] = {"documents": [], "audios": []}

        for doc in session.scalars(select(SourceDocument).where(SourceDocument.project_id == project_id)).all():
            raw = (doc.raw_text or "").strip()
            entry: dict[str, Any] = {"source_document_id": str(doc.id), "skipped": not bool(raw)}
            if not raw:
                out["documents"].append(entry)
                continue

            n_chunks = _count_document_chunks(session, doc.id)
            if n_chunks == 0:
                n_chunks = self._processing.chunk_source_document_sync(session, doc.id, strategy="fixed")
                session.flush()
                entry["chunked"] = True
                entry["chunk_count"] = n_chunks
            else:
                entry["chunked"] = False
                entry["chunk_count"] = n_chunks

            n_ent = _count_document_entities(session, doc.id)
            if n_ent == 0 and n_chunks > 0:
                created = self._extraction.extract_for_document_sync(session, doc.id)
                session.flush()
                entry["extracted"] = True
                entry["entities_created"] = created
            else:
                entry["extracted"] = False
                entry["entities_existing"] = n_ent

            out["documents"].append(entry)

        for audio in session.scalars(select(SourceAudio).where(SourceAudio.project_id == project_id)).all():
            entry: dict[str, Any] = {"source_audio_id": str(audio.id)}
            tr = _latest_completed_transcript(session, audio.id)
            if tr is None:
                entry["skipped"] = True
                entry["reason"] = "no_completed_transcript"
                out["audios"].append(entry)
                continue

            n_chunks = _count_audio_scope_chunks(session, audio.id)
            if n_chunks == 0:
                n_chunks = self._processing.chunk_transcript_sync(session, tr.id, strategy="fixed")
                session.flush()
                entry["chunked"] = True
                entry["chunk_count"] = n_chunks
            else:
                entry["chunked"] = False
                entry["chunk_count"] = n_chunks

            n_ent = _count_audio_scope_entities(session, audio.id)
            if n_ent == 0 and n_chunks > 0:
                created = self._extraction.extract_for_audio_sync(session, audio.id)
                session.flush()
                entry["extracted"] = True
                entry["entities_created"] = created
            else:
                entry["extracted"] = False
                entry["entities_existing"] = n_ent

            out["audios"].append(entry)

        logger.info("ensure_project_sources_pipeline_sync project_id=%s summary=%s", project_id, _prep_summary(out))
        return out

    def ensure_project_ready_for_report_sync(self, session: Session, project_id: UUID) -> dict[str, Any]:
        """Prepare sources, refresh aggregation snapshot, then caller may generate report."""
        prep = self.ensure_project_sources_pipeline_sync(session, project_id)
        self._aggregation.aggregate_project_sync(session, project_id)
        session.flush()
        logger.info(
            "ensure_project_ready_for_report_sync project_id=%s prep=%s aggregated=1",
            project_id,
            _prep_summary(prep),
        )
        return {"prep": prep, "aggregated": True}


def _prep_summary(prep: dict[str, Any]) -> dict[str, int]:
    docs = prep.get("documents") or []
    auds = prep.get("audios") or []
    chunked = sum(1 for x in docs if x.get("chunked")) + sum(1 for x in auds if x.get("chunked"))
    extracted = sum(1 for x in docs if x.get("extracted")) + sum(1 for x in auds if x.get("extracted"))
    skipped = sum(1 for x in auds if x.get("skipped"))
    return {"documents": len(docs), "audios": len(auds), "chunked": chunked, "extracted": extracted, "audios_skipped": skipped}
