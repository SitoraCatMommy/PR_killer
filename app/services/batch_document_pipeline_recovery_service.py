"""Detect stuck batch documents and queue full document pipeline (chunk + extract)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.settings import get_settings
from app.models.research_batch import ResearchBatch
from app.models.source_document import SourceDocument


def document_pipeline_actively_running(doc: SourceDocument) -> bool:
    """Another worker likely holds the row lock or is mid pipeline (fresh ``updated_at``)."""
    pipe = doc.pipeline_state_json or {}
    phase = str(pipe.get("phase") or "").strip().lower()
    if phase not in ("chunking", "extracting"):
        return False
    raw = pipe.get("updated_at")
    if not raw or not isinstance(raw, str):
        return False
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    ttl = int(get_settings().document_pipeline_active_ttl_seconds)
    age = datetime.now(timezone.utc) - ts
    return age < timedelta(seconds=ttl)


def document_pipeline_needs_recovery(doc: SourceDocument) -> bool:
    """True if document should be re-queued through ``pipeline_document_analysis``."""
    if document_pipeline_actively_running(doc):
        return False
    pipe = doc.pipeline_state_json or {}
    phase = str(pipe.get("phase") or "").strip().lower()
    ext_raw = pipe.get("extraction")
    ext = ext_raw if isinstance(ext_raw, dict) else {}
    ext_status = str(ext.get("status") or "").strip().lower()

    if ext_status in ("chunk_failed", "extraction_failed"):
        return True
    if phase == "failed":
        return True
    if phase in ("uploaded", "parsed", "chunking", "extracting"):
        return True
    if phase == "chunked":
        return ext_status not in ("ok", "completed_zero_entities", "skipped_no_chunks")
    if not phase and (doc.raw_text or "").strip():
        return True
    if phase == "extracted":
        return False
    return False


async def list_batch_documents_needing_recovery(
    session: AsyncSession,
    batch_id: UUID,
) -> tuple[list[UUID], list[UUID]]:
    """
    Returns ``(queued_ids, skipped_ok_ids)`` for document sources in the batch.
    """
    stmt = (
        select(ResearchBatch)
        .where(ResearchBatch.id == batch_id)
        .options(selectinload(ResearchBatch.sources))
    )
    batch = await session.scalar(stmt)
    if batch is None:
        return [], []

    queued: list[UUID] = []
    skipped: list[UUID] = []
    for row in batch.sources:
        did = row.source_document_id
        if did is None:
            continue
        doc = await session.get(SourceDocument, did)
        if doc is None:
            continue
        if document_pipeline_actively_running(doc):
            skipped.append(did)
            continue
        if document_pipeline_needs_recovery(doc):
            queued.append(did)
        else:
            skipped.append(did)
    return queued, skipped
