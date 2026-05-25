"""Sync helpers (Celery) to persist extraction / pipeline errors on ``SourceDocument``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified

from app.infrastructure.db_sync import sync_session_scope
from app.models.source_document import SourceDocument

logger = logging.getLogger(__name__)


def merge_document_pipeline_state(source_document_id: UUID, patch: dict[str, Any]) -> None:
    with sync_session_scope() as session:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            logger.warning("merge_document_pipeline_state: missing document %s", source_document_id)
            return
        base = dict(doc.pipeline_state_json or {})
        base.update(patch)
        doc.pipeline_state_json = base
        flag_modified(doc, "pipeline_state_json")


def record_extraction_outcome(
    source_document_id: UUID,
    *,
    status: str,
    reason: str | None,
    entities_created: int,
    chunk_count_hint: int | None = None,
) -> None:
    ext: dict[str, Any] = {
        "status": status,
        "reason": reason,
        "entities_created": int(entities_created),
    }
    if chunk_count_hint is not None:
        ext["chunk_count_at_extract"] = int(chunk_count_hint)
    merge_document_pipeline_state(
        source_document_id,
        {
            "extraction": ext,
        },
    )


def record_pipeline_failure(source_document_id: UUID, *, step: str, message: str) -> None:
    merge_document_pipeline_state(
        source_document_id,
        {
            "phase": "failed",
            "progress_percent": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "extraction": {
                "status": step,
                "reason": message[:2000],
                "entities_created": 0,
            },
            "last_error": {"step": step, "message": message[:2000]},
        },
    )
