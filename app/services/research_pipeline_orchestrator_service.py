"""Project-level pipeline: ensure chunking + extraction + aggregation before downstream steps."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import EntityType, JobStatus
from app.domain.pr_workspace import PR_SYNTHESIS_ENTITY_TYPES
from app.domain.research_constants import PERIOD_KEY_ALL_TIME, SNAPSHOT_TYPE_RESEARCH_ENTITIES
from app.infrastructure.settings import Settings, get_settings
from app.models.aggregation_snapshot import AggregationSnapshot
from app.models.extracted_entity import ExtractedEntity
from app.models.project import Project
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.services.processing_orchestrator_service import ProcessingOrchestratorService
from app.services.research_extraction_service import ExtractionService
from app.services.research_project_aggregation_service import ResearchAggregationService

logger = logging.getLogger(__name__)

_PR_ENTITY_TYPES = tuple(PR_SYNTHESIS_ENTITY_TYPES)


def _count_document_chunks(session: Session, source_document_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(TextChunk)
        .where(TextChunk.source_document_id == source_document_id)
    )
    return int(q or 0)


def _count_document_entities(session: Session, source_document_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(ExtractedEntity.source_document_id == source_document_id)
    )
    return int(q or 0)


def _count_document_pr_entities(session: Session, source_document_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(
            ExtractedEntity.source_document_id == source_document_id,
            ExtractedEntity.entity_type.in_(_PR_ENTITY_TYPES),
        )
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


def _count_audio_scope_pr_entities(session: Session, source_audio_id: UUID) -> int:
    t_sub = select(Transcript.id).where(Transcript.source_audio_id == source_audio_id)
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(
            or_(
                ExtractedEntity.source_audio_id == source_audio_id,
                ExtractedEntity.transcript_id.in_(t_sub),
            ),
            ExtractedEntity.entity_type.in_(_PR_ENTITY_TYPES),
        )
    )
    return int(q or 0)


def _count_project_chunks(session: Session, project_id: UUID) -> int:
    q = session.scalar(
        select(func.count()).select_from(TextChunk).where(TextChunk.project_id == project_id)
    )
    return int(q or 0)


def _count_project_entities(session: Session, project_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(ExtractedEntity.project_id == project_id)
    )
    return int(q or 0)


def _count_project_pr_entities(session: Session, project_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(
            ExtractedEntity.project_id == project_id,
            ExtractedEntity.entity_type.in_(_PR_ENTITY_TYPES),
        )
    )
    return int(q or 0)


def _count_project_supporting_facts(session: Session, project_id: UUID) -> int:
    q = session.scalar(
        select(func.count())
        .select_from(ExtractedEntity)
        .where(
            ExtractedEntity.project_id == project_id,
            ExtractedEntity.entity_type == EntityType.SUPPORTING_FACT,
        )
    )
    return int(q or 0)


def _aggregation_exists(session: Session, project_id: UUID) -> bool:
    q = session.scalar(
        select(func.count())
        .select_from(AggregationSnapshot)
        .where(
            AggregationSnapshot.project_id == project_id,
            AggregationSnapshot.snapshot_type == SNAPSHOT_TYPE_RESEARCH_ENTITIES,
            AggregationSnapshot.period_key == PERIOD_KEY_ALL_TIME,
        )
    )
    return int(q or 0) > 0


def build_pr_readiness_decision(
    *,
    processable_count: int,
    chunk_count: int,
    pr_entity_count: int,
    min_pr_entity_count: int,
    needs_chunking_count: int,
    needs_extraction_count: int,
    low_signal_source_count: int,
    aggregation_exists: bool,
) -> dict[str, Any]:
    """Pure readiness decision so tests can cover PR flow gating without a database."""
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    if processable_count == 0:
        blocking_reasons.append("no_processable_sources")
    if processable_count > 0 and chunk_count == 0:
        blocking_reasons.append("no_chunks")
    if chunk_count > 0 and pr_entity_count < min_pr_entity_count:
        blocking_reasons.append("low_pr_signal")
    if needs_chunking_count:
        warnings.append("sources_need_chunking")
    if needs_extraction_count:
        warnings.append("sources_need_extraction")
    if low_signal_source_count:
        warnings.append("sources_have_only_low_signal_entities")
    if pr_entity_count >= min_pr_entity_count and not aggregation_exists:
        warnings.append("aggregation_missing")
    return {
        "ready_for_report": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


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

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._processing = ProcessingOrchestratorService(self._settings)
        self._extraction: ExtractionService | None = None
        self._aggregation = ResearchAggregationService()

    @property
    def _extraction_service(self) -> ExtractionService:
        if self._extraction is None:
            self._extraction = ExtractionService()
        return self._extraction

    def inspect_project_pr_readiness_sync(
        self,
        session: Session,
        project_id: UUID,
    ) -> dict[str, Any]:
        """Read-only PR analysis readiness diagnostics for UI and report gating."""
        project = session.get(Project, project_id)
        if project is None:
            return {
                "project_found": False,
                "ready_for_report": False,
                "blocking_reasons": ["project_not_found"],
                "warnings": [],
                "source_count": 0,
                "processable_document_count": 0,
                "completed_transcript_audio_count": 0,
                "chunk_count": 0,
                "entity_count": 0,
                "pr_entity_count": 0,
                "supporting_fact_count": 0,
                "needs_chunking_count": 0,
                "needs_extraction_count": 0,
                "low_signal_source_count": 0,
                "aggregation_exists": False,
                "sources": [],
            }

        sources: list[dict[str, Any]] = []
        processable_document_count = 0
        completed_transcript_audio_count = 0
        needs_chunking_count = 0
        needs_extraction_count = 0
        low_signal_source_count = 0

        documents = session.scalars(
            select(SourceDocument)
            .where(SourceDocument.project_id == project_id)
            .order_by(SourceDocument.created_at)
        ).all()
        audios = session.scalars(
            select(SourceAudio)
            .where(SourceAudio.project_id == project_id)
            .order_by(SourceAudio.created_at)
        ).all()

        for doc in documents:
            has_text = bool((doc.raw_text or "").strip())
            chunks = _count_document_chunks(session, doc.id)
            entities = _count_document_entities(session, doc.id)
            pr_entities = _count_document_pr_entities(session, doc.id)
            needs_chunking = has_text and chunks == 0
            needs_extraction = chunks > 0 and entities == 0
            low_signal = chunks > 0 and entities > 0 and pr_entities == 0
            if has_text:
                processable_document_count += 1
            if needs_chunking:
                needs_chunking_count += 1
            if needs_extraction:
                needs_extraction_count += 1
            if low_signal:
                low_signal_source_count += 1
            sources.append(
                {
                    "source_kind": "document",
                    "source_id": str(doc.id),
                    "title": doc.filename,
                    "processable": has_text,
                    "chunk_count": chunks,
                    "entity_count": entities,
                    "pr_entity_count": pr_entities,
                    "needs_chunking": needs_chunking,
                    "needs_extraction": needs_extraction,
                    "low_signal": low_signal,
                    "reason": None if has_text else "document_has_no_text",
                }
            )

        for audio in audios:
            tr = _latest_completed_transcript(session, audio.id)
            has_text = bool(tr and (tr.full_text or "").strip())
            chunks = _count_audio_scope_chunks(session, audio.id)
            entities = _count_audio_scope_entities(session, audio.id)
            pr_entities = _count_audio_scope_pr_entities(session, audio.id)
            needs_chunking = has_text and chunks == 0
            needs_extraction = chunks > 0 and entities == 0
            low_signal = chunks > 0 and entities > 0 and pr_entities == 0
            if has_text:
                completed_transcript_audio_count += 1
            if needs_chunking:
                needs_chunking_count += 1
            if needs_extraction:
                needs_extraction_count += 1
            if low_signal:
                low_signal_source_count += 1
            sources.append(
                {
                    "source_kind": "audio",
                    "source_id": str(audio.id),
                    "title": audio.filename,
                    "processable": has_text,
                    "chunk_count": chunks,
                    "entity_count": entities,
                    "pr_entity_count": pr_entities,
                    "needs_chunking": needs_chunking,
                    "needs_extraction": needs_extraction,
                    "low_signal": low_signal,
                    "reason": None if has_text else "no_completed_transcript",
                }
            )

        source_count = len(documents) + len(audios)
        processable_count = processable_document_count + completed_transcript_audio_count
        chunk_count = _count_project_chunks(session, project_id)
        entity_count = _count_project_entities(session, project_id)
        pr_entity_count = _count_project_pr_entities(session, project_id)
        supporting_fact_count = _count_project_supporting_facts(session, project_id)
        has_aggregation = _aggregation_exists(session, project_id)

        decision = build_pr_readiness_decision(
            processable_count=processable_count,
            chunk_count=chunk_count,
            pr_entity_count=pr_entity_count,
            min_pr_entity_count=self._settings.pr_report_min_synthesis_entities,
            needs_chunking_count=needs_chunking_count,
            needs_extraction_count=needs_extraction_count,
            low_signal_source_count=low_signal_source_count,
            aggregation_exists=has_aggregation,
        )

        return {
            "project_found": True,
            "ready_for_report": decision["ready_for_report"],
            "blocking_reasons": decision["blocking_reasons"],
            "warnings": decision["warnings"],
            "source_count": source_count,
            "processable_document_count": processable_document_count,
            "completed_transcript_audio_count": completed_transcript_audio_count,
            "chunk_count": chunk_count,
            "entity_count": entity_count,
            "pr_entity_count": pr_entity_count,
            "supporting_fact_count": supporting_fact_count,
            "needs_chunking_count": needs_chunking_count,
            "needs_extraction_count": needs_extraction_count,
            "low_signal_source_count": low_signal_source_count,
            "aggregation_exists": has_aggregation,
            "min_pr_entity_count": self._settings.pr_report_min_synthesis_entities,
            "sources": sources,
        }

    def prepare_project_for_pr_report_sync(
        self,
        session: Session,
        project_id: UUID,
        *,
        max_auto_extract_chunks: int,
        auto_prepare: bool = True,
    ) -> dict[str, Any]:
        """Bounded preparation for report generation; avoids surprise large GPT extraction."""
        out: dict[str, Any] = {
            "documents": [],
            "audios": [],
            "blocked": False,
            "blocking_reasons": [],
            "auto_prepare": auto_prepare,
            "max_auto_extract_chunks": max_auto_extract_chunks,
        }
        if session.get(Project, project_id) is None:
            out["blocked"] = True
            out["blocking_reasons"].append("project_not_found")
            return out
        if not auto_prepare:
            out["skipped"] = "auto_prepare_disabled"
            return out

        # First do cheap deterministic chunking so extraction cost can be estimated accurately.
        document_stmt = select(SourceDocument).where(SourceDocument.project_id == project_id)
        for doc in session.scalars(document_stmt).all():
            raw = (doc.raw_text or "").strip()
            entry: dict[str, Any] = {"source_document_id": str(doc.id), "skipped": not bool(raw)}
            if raw:
                n_chunks = _count_document_chunks(session, doc.id)
                if n_chunks == 0:
                    n_chunks = self._processing.chunk_source_document_sync(
                        session,
                        doc.id,
                        strategy="fixed",
                    )
                    session.flush()
                    entry["chunked"] = True
                else:
                    entry["chunked"] = False
                entry["chunk_count"] = n_chunks
                entry["entities_existing"] = _count_document_entities(session, doc.id)
                entry["pr_entities_existing"] = _count_document_pr_entities(session, doc.id)
            out["documents"].append(entry)

        audio_stmt = select(SourceAudio).where(SourceAudio.project_id == project_id)
        for audio in session.scalars(audio_stmt).all():
            audio_entry: dict[str, Any] = {"source_audio_id": str(audio.id)}
            tr = _latest_completed_transcript(session, audio.id)
            if tr is None:
                audio_entry["skipped"] = True
                audio_entry["reason"] = "no_completed_transcript"
                out["audios"].append(audio_entry)
                continue
            n_chunks = _count_audio_scope_chunks(session, audio.id)
            if n_chunks == 0:
                n_chunks = self._processing.chunk_transcript_sync(session, tr.id, strategy="fixed")
                session.flush()
                audio_entry["chunked"] = True
            else:
                audio_entry["chunked"] = False
            audio_entry["chunk_count"] = n_chunks
            audio_entry["entities_existing"] = _count_audio_scope_entities(session, audio.id)
            audio_entry["pr_entities_existing"] = _count_audio_scope_pr_entities(session, audio.id)
            out["audios"].append(audio_entry)

        chunks_to_extract = 0
        for entry in out["documents"]:
            if entry.get("chunk_count", 0) > 0 and entry.get("entities_existing", 0) == 0:
                chunks_to_extract += int(entry["chunk_count"])
        for entry in out["audios"]:
            if entry.get("chunk_count", 0) > 0 and entry.get("entities_existing", 0) == 0:
                chunks_to_extract += int(entry["chunk_count"])
        out["chunks_to_auto_extract"] = chunks_to_extract

        if (
            self._settings.research_extraction_provider == "gpt"
            and chunks_to_extract > max_auto_extract_chunks
        ):
            out["blocked"] = True
            out["blocking_reasons"].append("auto_extract_chunk_cap_exceeded")
            logger.warning(
                "prepare_project_for_pr_report_sync blocked project_id=%s "
                "chunks_to_extract=%s cap=%s",
                project_id,
                chunks_to_extract,
                max_auto_extract_chunks,
            )
            return out

        for entry in out["documents"]:
            if entry.get("chunk_count", 0) > 0 and entry.get("entities_existing", 0) == 0:
                created = self._extraction_service.extract_for_document_sync(
                    session,
                    UUID(str(entry["source_document_id"])),
                )
                session.flush()
                entry["extracted"] = True
                entry["entities_created"] = created
            else:
                entry["extracted"] = False

        for entry in out["audios"]:
            if entry.get("chunk_count", 0) > 0 and entry.get("entities_existing", 0) == 0:
                created = self._extraction_service.extract_for_audio_sync(
                    session,
                    UUID(str(entry["source_audio_id"])),
                )
                session.flush()
                entry["extracted"] = True
                entry["entities_created"] = created
            else:
                entry["extracted"] = False

        if _count_project_entities(session, project_id) > 0:
            self._aggregation.aggregate_project_sync(session, project_id)
            session.flush()
            out["aggregated"] = True
        else:
            out["aggregated"] = False
        logger.info(
            "prepare_project_for_pr_report_sync project_id=%s blocked=%s summary=%s",
            project_id,
            out["blocked"],
            _prep_summary(out),
        )
        return out

    def ensure_project_sources_pipeline_sync(
        self,
        session: Session,
        project_id: UUID,
    ) -> dict[str, Any]:
        """Chunk (if needed) and extract (if no entities) for every text/audio source with data."""
        out: dict[str, Any] = {"documents": [], "audios": []}

        document_stmt = select(SourceDocument).where(SourceDocument.project_id == project_id)
        for doc in session.scalars(document_stmt).all():
            raw = (doc.raw_text or "").strip()
            entry: dict[str, Any] = {"source_document_id": str(doc.id), "skipped": not bool(raw)}
            if not raw:
                out["documents"].append(entry)
                continue

            n_chunks = _count_document_chunks(session, doc.id)
            if n_chunks == 0:
                n_chunks = self._processing.chunk_source_document_sync(
                    session,
                    doc.id,
                    strategy="fixed",
                )
                session.flush()
                entry["chunked"] = True
                entry["chunk_count"] = n_chunks
            else:
                entry["chunked"] = False
                entry["chunk_count"] = n_chunks

            n_ent = _count_document_entities(session, doc.id)
            if n_ent == 0 and n_chunks > 0:
                created = self._extraction_service.extract_for_document_sync(session, doc.id)
                session.flush()
                entry["extracted"] = True
                entry["entities_created"] = created
            else:
                entry["extracted"] = False
                entry["entities_existing"] = n_ent

            out["documents"].append(entry)

        audio_stmt = select(SourceAudio).where(SourceAudio.project_id == project_id)
        for audio in session.scalars(audio_stmt).all():
            audio_entry: dict[str, Any] = {"source_audio_id": str(audio.id)}
            tr = _latest_completed_transcript(session, audio.id)
            if tr is None:
                audio_entry["skipped"] = True
                audio_entry["reason"] = "no_completed_transcript"
                out["audios"].append(audio_entry)
                continue

            n_chunks = _count_audio_scope_chunks(session, audio.id)
            if n_chunks == 0:
                n_chunks = self._processing.chunk_transcript_sync(session, tr.id, strategy="fixed")
                session.flush()
                audio_entry["chunked"] = True
                audio_entry["chunk_count"] = n_chunks
            else:
                audio_entry["chunked"] = False
                audio_entry["chunk_count"] = n_chunks

            n_ent = _count_audio_scope_entities(session, audio.id)
            if n_ent == 0 and n_chunks > 0:
                created = self._extraction_service.extract_for_audio_sync(session, audio.id)
                session.flush()
                audio_entry["extracted"] = True
                audio_entry["entities_created"] = created
            else:
                audio_entry["extracted"] = False
                audio_entry["entities_existing"] = n_ent

            out["audios"].append(audio_entry)

        logger.info(
            "ensure_project_sources_pipeline_sync project_id=%s summary=%s",
            project_id,
            _prep_summary(out),
        )
        return out

    def ensure_project_ready_for_report_sync(
        self,
        session: Session,
        project_id: UUID,
    ) -> dict[str, Any]:
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
    chunked = sum(1 for x in docs if x.get("chunked")) + sum(
        1 for x in auds if x.get("chunked")
    )
    extracted = sum(1 for x in docs if x.get("extracted")) + sum(
        1 for x in auds if x.get("extracted")
    )
    skipped = sum(1 for x in auds if x.get("skipped"))
    return {
        "documents": len(docs),
        "audios": len(auds),
        "chunked": chunked,
        "extracted": extracted,
        "audios_skipped": skipped,
    }
