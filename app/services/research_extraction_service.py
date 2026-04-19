"""Research-domain extraction: TextChunk → ExtractedEntity (sync for Celery / transactional)."""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import EntityType, JobStatus
from app.models.extracted_entity import ExtractedEntity
from app.models.source_document import SourceDocument
from app.models.source_audio import SourceAudio
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.repositories.research_entity_repository import (
    stmt_delete_extracted_entities_for_audio_scope,
    stmt_delete_extracted_entities_for_document,
    stmt_delete_extracted_entities_for_transcript,
)
from app.repositories.text_chunk_repository import (
    stmt_chunks_for_audio_scope_ordered,
    stmt_chunks_for_document_ordered,
    stmt_chunks_for_transcript_ordered,
)
from app.schemas.research_extraction import ExtractedEntityCandidate
from app.services.extraction import mock_provider as _mock_mp
from app.services.extraction.provider import ResearchExtractionProvider, get_extraction_provider
from app.services.processing_orchestrator_service import ProcessingOrchestratorService

logger = logging.getLogger(__name__)

_MAX_ENTITY_CONTENT_LEN = 300


class ExtractionService:
    """Load chunks for a source surface, run provider, replace ExtractedEntity rows."""

    def __init__(self, provider: ResearchExtractionProvider | None = None) -> None:
        self._provider = provider or get_extraction_provider()
        logger.info(
            "ExtractionService provider_class=%s",
            type(self._provider).__qualname__,
        )

    def _persist(
        self,
        session: Session,
        chunk: TextChunk,
        filename_hint: str | None,
        candidates: list[ExtractedEntityCandidate],
    ) -> int:
        n = 0
        for cand in candidates:
            session.add(
                ExtractedEntity(
                    project_id=chunk.project_id,
                    source_document_id=chunk.source_document_id,
                    source_audio_id=chunk.source_audio_id,
                    transcript_id=chunk.transcript_id,
                    chunk_id=chunk.id,
                    entity_type=cand.entity_type,
                    title=cand.title,
                    content=cand.content,
                    confidence_score=cand.confidence_score,
                    tags_json=dict(cand.tags_json),
                    evidence_json=dict(cand.evidence_json),
                )
            )
            n += 1
        return n

    @staticmethod
    def _fallback_confidence(chunk_index: int, slot: int) -> float:
        h = hashlib.sha256(f"svc-sentence-fallback:{chunk_index}:{slot}".encode()).hexdigest()
        n = int(h[:8], 16) % 351
        return round(min(0.95, 0.6 + n / 1000.0), 3)

    def _filter_provider_candidates(
        self,
        ch: TextChunk,
        raw: list[ExtractedEntityCandidate],
    ) -> list[ExtractedEntityCandidate]:
        chunk_text = (ch.text or "").strip()
        accepted: list[ExtractedEntityCandidate] = []
        for cand in raw:
            content = (cand.content or "").strip()
            if len(content) > _MAX_ENTITY_CONTENT_LEN:
                logger.warning(
                    "ExtractionService rejected candidate chunk_id=%s reason=content_too_long len=%s preview=%r",
                    ch.id,
                    len(content),
                    content[:80],
                )
                continue
            if chunk_text and content == chunk_text:
                logger.warning(
                    "ExtractionService rejected candidate chunk_id=%s reason=content_equals_full_chunk",
                    ch.id,
                )
                continue
            accepted.append(cand)
        return accepted

    def _existing_spans(self, entities: list[ExtractedEntityCandidate]) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for c in entities:
            ev = c.evidence_json or {}
            try:
                s0 = int(ev.get("span_start", 0))
                s1 = int(ev.get("span_end", 0))
            except (TypeError, ValueError):
                continue
            spans.append((s0, s1))
        return spans

    @staticmethod
    def _spans_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
        return not (a1 <= b0 or a0 >= b1)

    def _sentence_level_fallback(
        self,
        ch: TextChunk,
        filename_hint: str | None,
    ) -> list[ExtractedEntityCandidate]:
        chunk_text = (ch.text or "").strip()
        if not chunk_text:
            return []

        out: list[ExtractedEntityCandidate] = []
        slot = 0
        for sent, s0, s1 in _mock_mp._split_sentences(chunk_text)[:8]:
            slot += 1
            clipped = _mock_mp._clip(sent, _MAX_ENTITY_CONTENT_LEN)
            out.append(
                ExtractedEntityCandidate(
                    entity_type=EntityType.SUPPORTING_FACT,
                    title=_mock_mp._title_from_sentence(sent, "Statement"),
                    content=clipped,
                    confidence_score=self._fallback_confidence(ch.chunk_index, slot),
                    tags_json={
                        "rule": "service_sentence_fallback",
                        "source_file": filename_hint or "",
                    },
                    evidence_json={
                        "quote": clipped,
                        "span_start": s0,
                        "span_end": s1,
                        "provider": "service_sentence_fallback",
                    },
                )
            )

        if len(out) < 3 and len(chunk_text) >= 30:
            existing = self._existing_spans(out)
            n_seg = min(6, max(3, (len(chunk_text) + 99) // 100))
            for a, b in _mock_mp._even_segments(chunk_text, n_seg):
                if len(out) >= 8:
                    break
                if any(self._spans_overlap(a, b, x, y) for x, y in existing):
                    continue
                snippet = chunk_text[a:b].strip()
                if len(snippet) < 12:
                    continue
                if snippet == chunk_text.strip():
                    continue
                slot += 1
                clipped = _mock_mp._clip(snippet, _MAX_ENTITY_CONTENT_LEN)
                out.append(
                    ExtractedEntityCandidate(
                        entity_type=EntityType.SUPPORTING_FACT,
                        title=_mock_mp._title_from_sentence(snippet, "Segment"),
                        content=clipped,
                        confidence_score=self._fallback_confidence(ch.chunk_index, slot),
                        tags_json={
                            "rule": "service_segment_fallback",
                            "source_file": filename_hint or "",
                        },
                        evidence_json={
                            "quote": clipped,
                            "span_start": a,
                            "span_end": b,
                            "provider": "service_sentence_fallback",
                        },
                    )
                )
                existing.append((a, b))

        if not out and chunk_text:
            slot += 1
            clipped = _mock_mp._clip(chunk_text, _MAX_ENTITY_CONTENT_LEN)
            out.append(
                ExtractedEntityCandidate(
                    entity_type=EntityType.SUPPORTING_FACT,
                    title=_mock_mp._title_from_sentence(chunk_text, "Chunk"),
                    content=clipped,
                    confidence_score=self._fallback_confidence(ch.chunk_index, slot),
                    tags_json={"rule": "service_tiny_chunk", "source_file": filename_hint or ""},
                    evidence_json={
                        "quote": clipped,
                        "span_start": 0,
                        "span_end": len(chunk_text),
                        "provider": "service_sentence_fallback",
                    },
                )
            )

        out.sort(
            key=lambda c: (
                int((c.evidence_json or {}).get("span_start", 0)),
                int((c.evidence_json or {}).get("span_end", 0)),
                c.entity_type.value,
            )
        )
        if len(out) > 8:
            out[:] = out[:8]
        return out

    def _supplement_sparse(
        self,
        ch: TextChunk,
        entities: list[ExtractedEntityCandidate],
        filename_hint: str | None,
    ) -> list[ExtractedEntityCandidate]:
        chunk_text = (ch.text or "").strip()
        if len(entities) >= 3 or len(chunk_text) < 30:
            return entities

        existing = self._existing_spans(entities)
        out = list(entities)
        slot_base = len(out)
        n_seg = min(6, max(3, (len(chunk_text) + 99) // 100))
        for a, b in _mock_mp._even_segments(chunk_text, n_seg):
            if len(out) >= 8:
                break
            if any(self._spans_overlap(a, b, x, y) for x, y in existing):
                continue
            snippet = chunk_text[a:b].strip()
            if len(snippet) < 12:
                continue
            if snippet == chunk_text.strip():
                continue
            slot_base += 1
            clipped = _mock_mp._clip(snippet, _MAX_ENTITY_CONTENT_LEN)
            out.append(
                ExtractedEntityCandidate(
                    entity_type=EntityType.SUPPORTING_FACT,
                    title=_mock_mp._title_from_sentence(snippet, "Segment"),
                    content=clipped,
                    confidence_score=self._fallback_confidence(ch.chunk_index, slot_base),
                    tags_json={
                        "rule": "service_supplement_segment",
                        "source_file": filename_hint or "",
                    },
                    evidence_json={
                        "quote": clipped,
                        "span_start": a,
                        "span_end": b,
                        "provider": "service_supplement",
                    },
                )
            )
            existing.append((a, b))
            if len(out) >= 3:
                break

        out.sort(
            key=lambda c: (
                int((c.evidence_json or {}).get("span_start", 0)),
                int((c.evidence_json or {}).get("span_end", 0)),
                c.entity_type.value,
            )
        )
        if len(out) > 8:
            out[:] = out[:8]
        return out

    def _finalize_chunk_entities(
        self,
        ch: TextChunk,
        raw_from_provider: list[ExtractedEntityCandidate],
        filename_hint: str | None,
    ) -> list[ExtractedEntityCandidate]:
        chunk_text = (ch.text or "").strip()

        if len(raw_from_provider) <= 1:
            final = self._sentence_level_fallback(ch, filename_hint)
        else:
            final = self._filter_provider_candidates(ch, raw_from_provider)
            if len(final) <= 1:
                final = self._sentence_level_fallback(ch, filename_hint)
            else:
                final = self._supplement_sparse(ch, final, filename_hint)

        if len(final) < 3 and len(chunk_text) >= 30:
            final = self._supplement_sparse(ch, final, filename_hint)

        if len(final) > 8:
            final = final[:8]
        return final

    def _extract_for_chunks(
        self,
        session: Session,
        chunks: list[TextChunk],
        *,
        filename_hint: str | None,
    ) -> int:
        total = 0
        for ch in chunks:
            chunk_preview = (ch.text or "")[:100]
            try:
                raw = self._provider.extract_from_chunk(
                    text=ch.text,
                    chunk_index=ch.chunk_index,
                    source_filename=filename_hint,
                )
            except Exception:
                logger.exception("Extraction provider failed for chunk %s", ch.id)
                raise
            logger.info(
                "ExtractionService chunk_id=%s provider_class=%s provider_entity_count=%s text_preview=%r",
                ch.id,
                type(self._provider).__qualname__,
                len(raw),
                chunk_preview,
            )
            candidates = self._finalize_chunk_entities(ch, raw, filename_hint)
            logger.debug("ExtractionService chunk_id=%s finalized_entity_count=%s", ch.id, len(candidates))
            total += self._persist(session, ch, filename_hint, candidates)
        return total

    def extract_for_document_sync(self, session: Session, source_document_id: UUID) -> int:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            raise ValueError("source_document_not_found")

        chunks = list(session.scalars(stmt_chunks_for_document_ordered(source_document_id)).all())
        if not chunks and (doc.raw_text or "").strip():
            orch = ProcessingOrchestratorService()
            orch.chunk_source_document_sync(session, source_document_id, strategy="fixed")
            session.flush()
            chunks = list(session.scalars(stmt_chunks_for_document_ordered(source_document_id)).all())
            logger.info(
                "extract_for_document_sync: auto_chunked document_id=%s chunk_count=%s",
                source_document_id,
                len(chunks),
            )

        session.execute(stmt_delete_extracted_entities_for_document(source_document_id))
        session.flush()

        if not chunks:
            logger.info("No text chunks for document %s; skipping extraction", source_document_id)
            return 0

        n = self._extract_for_chunks(session, chunks, filename_hint=doc.filename)
        session.flush()
        return n

    def extract_for_transcript_sync(self, session: Session, transcript_id: UUID) -> int:
        tr = session.get(Transcript, transcript_id)
        if tr is None:
            raise ValueError("transcript_not_found")

        audio = session.get(SourceAudio, tr.source_audio_id)
        filename_hint = audio.filename if audio else None

        chunks = list(session.scalars(stmt_chunks_for_transcript_ordered(transcript_id)).all())
        auto_chunked = False
        if not chunks:
            orch = ProcessingOrchestratorService()
            orch.chunk_transcript_sync(session, transcript_id, strategy="fixed")
            session.flush()
            auto_chunked = True
            chunks = list(session.scalars(stmt_chunks_for_transcript_ordered(transcript_id)).all())

        logger.info(
            "extract_for_transcript_sync: transcript_id=%s chunk_count=%s auto_chunked=%s",
            transcript_id,
            len(chunks),
            auto_chunked,
        )

        if not chunks:
            logger.warning(
                "extract_for_transcript_sync: no chunks after ensure; skipping extraction transcript_id=%s",
                transcript_id,
            )
            return 0

        session.execute(stmt_delete_extracted_entities_for_transcript(transcript_id))
        session.flush()

        n = self._extract_for_chunks(session, chunks, filename_hint=filename_hint)
        session.flush()
        return n

    def extract_for_audio_sync(self, session: Session, source_audio_id: UUID) -> int:
        audio = session.get(SourceAudio, source_audio_id)
        if audio is None:
            raise ValueError("source_audio_not_found")

        chunks = list(session.scalars(stmt_chunks_for_audio_scope_ordered(source_audio_id)).all())
        if not chunks:
            tr = session.scalar(
                select(Transcript)
                .where(
                    Transcript.source_audio_id == source_audio_id,
                    Transcript.status == JobStatus.COMPLETED,
                )
                .order_by(Transcript.created_at.desc())
                .limit(1)
            )
            if tr is not None:
                orch = ProcessingOrchestratorService()
                orch.chunk_transcript_sync(session, tr.id, strategy="fixed")
                session.flush()
                chunks = list(session.scalars(stmt_chunks_for_audio_scope_ordered(source_audio_id)).all())
                logger.info(
                    "extract_for_audio_sync: auto_chunked_transcript audio_id=%s transcript_id=%s chunk_count=%s",
                    source_audio_id,
                    tr.id,
                    len(chunks),
                )

        session.execute(stmt_delete_extracted_entities_for_audio_scope(source_audio_id))
        session.flush()

        if not chunks:
            logger.info("No text chunks for audio %s; skipping extraction", source_audio_id)
            return 0

        n = self._extract_for_chunks(session, chunks, filename_hint=audio.filename)
        session.flush()
        return n
