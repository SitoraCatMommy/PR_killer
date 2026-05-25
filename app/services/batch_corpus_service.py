"""Collect `TextChunk` rows for a `ResearchBatch` in stable order (batch source order → chunk index).

Use this module for any downstream LLM / export path that needs the full text of a selected study.
See ``docs/transcript_storage.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.research_batch import ResearchBatch
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.repositories.text_chunk_repository import (
    TextChunkRepository,
    stmt_chunks_for_audio_scope_ordered,
    stmt_chunks_for_document_ordered,
)


def resolve_transcript_ids_sync(session: Session, audio_ids: Sequence[UUID]) -> list[UUID]:
    """Transcript primary keys for the given source audio IDs (may be empty)."""
    if not audio_ids:
        return []
    rows = session.scalars(select(Transcript.id).where(Transcript.source_audio_id.in_(audio_ids))).all()
    return list(rows)


async def resolve_transcript_ids_async(session: AsyncSession, audio_ids: Sequence[UUID]) -> list[UUID]:
    if not audio_ids:
        return []
    rows = (await session.scalars(select(Transcript.id).where(Transcript.source_audio_id.in_(audio_ids)))).all()
    return list(rows)


def text_chunks_scope_and(
    project_id: UUID,
    *,
    document_ids: Sequence[UUID] | None = None,
    audio_ids: Sequence[UUID] | None = None,
    transcript_ids: Sequence[UUID] | None = None,
) -> ColumnElement:
    """``WHERE`` fragment: same project and chunk belongs to any given source surface."""
    doc_ids = list(document_ids or [])
    aud_ids = list(audio_ids or [])
    trn_ids = list(transcript_ids or [])
    parts: list[ColumnElement] = []
    if doc_ids:
        parts.append(TextChunk.source_document_id.in_(doc_ids))
    if aud_ids:
        parts.append(TextChunk.source_audio_id.in_(aud_ids))
    if trn_ids:
        parts.append(TextChunk.transcript_id.in_(trn_ids))
    if not parts:
        return false()
    return and_(TextChunk.project_id == project_id, or_(*parts))


def stmt_text_chunks_for_batch_surfaces(
    project_id: UUID,
    *,
    document_ids: Sequence[UUID],
    audio_ids: Sequence[UUID],
    transcript_ids: Sequence[UUID],
) -> Select[tuple[TextChunk]]:
    """Single-query fetch of all chunks in a batch (unordered — use for search/aggregates, not LLM concat)."""
    scope = text_chunks_scope_and(
        project_id,
        document_ids=document_ids,
        audio_ids=audio_ids,
        transcript_ids=transcript_ids,
    )
    return select(TextChunk).where(scope)


def list_text_chunks_for_batch_ordered_sync(session: Session, batch: ResearchBatch) -> list[TextChunk]:
    """Batch sources ordered by ``created_at``, then chunks per source by ``chunk_index``."""
    sources = sorted(batch.sources, key=lambda s: (s.created_at, s.id))
    out: list[TextChunk] = []
    for s in sources:
        if s.source_document_id is not None:
            out.extend(session.scalars(stmt_chunks_for_document_ordered(s.source_document_id)).all())
        elif s.source_audio_id is not None:
            out.extend(session.scalars(stmt_chunks_for_audio_scope_ordered(s.source_audio_id)).all())
    return out


async def list_text_chunks_for_batch_ordered(session: AsyncSession, batch: ResearchBatch) -> list[TextChunk]:
    sources = sorted(batch.sources, key=lambda s: (s.created_at, s.id))
    repo = TextChunkRepository(session)
    out: list[TextChunk] = []
    for s in sources:
        if s.source_document_id is not None:
            out.extend(await repo.list_for_document_ordered(s.source_document_id))
        elif s.source_audio_id is not None:
            out.extend(await repo.list_for_audio_scope_ordered(s.source_audio_id))
    return out


def merged_corpus_text_for_batch_sync(
    session: Session,
    batch: ResearchBatch,
    *,
    separator: str = "\n\n",
) -> str:
    chunks = list_text_chunks_for_batch_ordered_sync(session, batch)
    parts = [c.text.strip() for c in chunks if (c.text or "").strip()]
    return separator.join(parts)


async def merged_corpus_text_for_batch(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    separator: str = "\n\n",
) -> str:
    chunks = await list_text_chunks_for_batch_ordered(session, batch)
    parts = [c.text.strip() for c in chunks if (c.text or "").strip()]
    return separator.join(parts)


async def build_batch_corpus_preview(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    max_chars: int,
    separator: str = "\n\n",
) -> dict[str, int | str | bool]:
    """Ordered chunk merge for API/UI; truncates ``text`` when corpus exceeds ``max_chars``."""
    chunks = await list_text_chunks_for_batch_ordered(session, batch)
    parts = [c.text.strip() for c in chunks if (c.text or "").strip()]
    merged = separator.join(parts)
    total = len(merged)
    truncated = total > max_chars
    preview = merged[:max_chars] if truncated else merged
    return {
        "chunk_count": len(chunks),
        "total_character_count": total,
        "max_chars_applied": max_chars,
        "truncated": truncated,
        "text": preview,
    }
