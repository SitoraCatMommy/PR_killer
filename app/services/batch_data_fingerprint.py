"""Stable fingerprint of batch corpora for LLM cache invalidation when evidence changes."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extracted_entity import ExtractedEntity
from app.models.research_batch import ResearchBatch
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.services.batch_corpus_service import text_chunks_scope_and


async def compute_batch_corpora_fingerprint(session: AsyncSession, batch: ResearchBatch) -> str:
    """Hash entity + chunk counts and max timestamps scoped to batch sources."""
    doc_ids = [s.source_document_id for s in batch.sources if s.source_document_id]
    audio_ids = [s.source_audio_id for s in batch.sources if s.source_audio_id]
    transcript_ids: list[UUID] = []
    if audio_ids:
        tid_stmt = select(Transcript.id).where(Transcript.source_audio_id.in_(audio_ids))
        transcript_ids = list((await session.scalars(tid_stmt)).all())

    if not doc_ids and not audio_ids:
        return "empty"

    parts: list[Any] = []
    if doc_ids:
        parts.append(ExtractedEntity.source_document_id.in_(doc_ids))
    if audio_ids:
        parts.append(ExtractedEntity.source_audio_id.in_(audio_ids))
    if transcript_ids:
        parts.append(ExtractedEntity.transcript_id.in_(transcript_ids))
    surface_filter = or_(*parts)

    ent_stmt = (
        select(func.count(), func.max(ExtractedEntity.updated_at))
        .select_from(ExtractedEntity)
        .where(
            ExtractedEntity.project_id == batch.project_id,
            ExtractedEntity.canonical_entity_id.is_(None),
            surface_filter,
        )
    )
    ent_row = (await session.execute(ent_stmt)).one()
    ent_cnt = int(ent_row[0] or 0)
    ent_max = ent_row[1]
    ent_max_s = ent_max.isoformat() if ent_max is not None else "none"

    chunk_scope = text_chunks_scope_and(
        batch.project_id,
        document_ids=list(doc_ids),
        audio_ids=list(audio_ids),
        transcript_ids=transcript_ids,
    )
    ch_stmt = select(func.count(), func.max(TextChunk.created_at)).select_from(TextChunk).where(chunk_scope)
    ch_row = (await session.execute(ch_stmt)).one()
    ch_cnt = int(ch_row[0] or 0)
    ch_max = ch_row[1]
    ch_max_s = ch_max.isoformat() if ch_max is not None else "none"

    raw = f"v1|e:{ent_cnt}|{ent_max_s}|c:{ch_cnt}|{ch_max_s}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


async def compute_project_corpora_fingerprint(session: AsyncSession, project_id: UUID) -> str:
    """Hash entity + chunk counts for all sources in a project."""
    doc_ids = list(
        (await session.scalars(select(SourceDocument.id).where(SourceDocument.project_id == project_id))).all()
    )
    audio_ids = list(
        (await session.scalars(select(SourceAudio.id).where(SourceAudio.project_id == project_id))).all()
    )
    if not doc_ids and not audio_ids:
        return "empty"
    view = type(
        "ProjectCorpusView",
        (),
        {
            "project_id": project_id,
            "sources": [type("S", (), {"source_document_id": d, "source_audio_id": None})() for d in doc_ids]
            + [type("S", (), {"source_document_id": None, "source_audio_id": a})() for a in audio_ids],
        },
    )()
    return await compute_batch_corpora_fingerprint(session, view)  # type: ignore[arg-type]
