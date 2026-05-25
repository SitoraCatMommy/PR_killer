"""Persist interview_units rows from heuristic/LLM splits (sync, Celery-safe)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete

from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.interview_unit import InterviewUnit
from app.models.source_document import SourceDocument
from app.services.batch_queue_service import BATCH_ANALYSIS_META_KEY
from app.services.interview_unit_split_service import build_interview_unit_drafts, drafts_to_rows

logger = logging.getLogger(__name__)


def sync_interview_units_for_document_sync(source_document_id: UUID) -> None:
    """Replace interview_units for a document from ``raw_text`` using batch multi-interview flag when present."""
    try:
        with sync_session_scope() as session:
            doc = session.get(SourceDocument, source_document_id)
            if doc is None:
                return
            raw = (doc.raw_text or "").strip()
            if not raw:
                return
            meta = dict(doc.metadata_json or {})
            ba = meta.get(BATCH_ANALYSIS_META_KEY)
            multi = True
            if isinstance(ba, dict) and "single_file_multi_interview_mode" in ba:
                multi = bool(ba["single_file_multi_interview_mode"])
            drafts = build_interview_unit_drafts(raw, multi_interview_mode=multi, settings=get_settings())
            rows = drafts_to_rows(drafts, project_id=doc.project_id, source_document_id=doc.id)
            session.execute(delete(InterviewUnit).where(InterviewUnit.source_document_id == doc.id))
            for row in rows:
                session.add(InterviewUnit(**row))
    except Exception:
        logger.exception("sync_interview_units_for_document_sync failed doc=%s", source_document_id)
