from __future__ import annotations

import logging
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.enums import (
    DashboardAggregateKind,
    EntityKind,
    MaterialType,
    ProcessingStatus,
)
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.models.dashboard_aggregate import DashboardAggregate
from app.models.material_extracted_entity import MaterialExtractedEntity
from app.models.insight import INSIGHT_EMBEDDING_DIMENSION, Insight
from app.models.insight_source_link import InsightSourceLink
from app.models.material import Material
from app.repositories.entity_repository import entity_fingerprint
from app.services.deduplication_service import DeduplicationService
from app.services.entity_extraction_service import EntityExtractionService
from app.services.normalization_service import NormalizationService
from app.services.transcription_service import TranscriptionService

logger = logging.getLogger(__name__)


def _upsert_entities_sync(session: Session, material_id: UUID, entities: list[dict]) -> int:
    inserted = 0
    for e in entities:
        kind = EntityKind(e["kind"])
        label = str(e["label"])
        nv = e.get("normalized_value")
        ss = e.get("span_start")
        se = e.get("span_end")
        fp = entity_fingerprint(kind, label, nv, ss, se)
        stmt = (
            insert(MaterialExtractedEntity)
            .values(
                id=uuid.uuid4(),
                material_id=material_id,
                kind=kind,
                label=label,
                normalized_value=nv,
                span_start=ss,
                span_end=se,
                payload=dict(e.get("payload") or {}),
                fingerprint=fp,
            )
            .on_conflict_do_nothing(constraint="uq_entity_material_fingerprint")
        )
        res = session.execute(stmt)
        if res.rowcount:
            inserted += 1
    return inserted


def _ensure_stub_insight_sync(session: Session, material: Material, normalized: str) -> None:
    """Create one dashboard-ready insight linked to the material; dedupe by hash."""
    headline = (material.title or "Research note")[:512]
    summary = normalized[:2000] if normalized else None
    dedup = DeduplicationService.insight_dedup_key(
        headline=headline,
        summary=summary,
        material_id=material.id,
        locator={"material_id": str(material.id)},
    )
    existing = session.scalar(select(Insight).where(Insight.dedup_key == dedup))
    if existing:
        return
    placeholder_embedding = [0.0] * INSIGHT_EMBEDDING_DIMENSION
    insight = Insight(
        headline=headline,
        summary=summary,
        body=normalized[:8000] if normalized else None,
        confidence=0.5,
        dedup_key=dedup,
        embedding=placeholder_embedding,
        embedding_model="stub-zeros",
    )
    link = InsightSourceLink(
        insight=insight,
        material_id=material.id,
        span_start=0,
        span_end=min(len(normalized), 4096) if normalized else None,
        quote=normalized[:512] if normalized else None,
        locator={"material_id": str(material.id)},
    )
    session.add(insight)
    session.add(link)


@celery_app.task(name="app.workers.tasks.pipeline.process_material_pipeline", bind=True)
def process_material_pipeline(self, material_id: str) -> dict[str, str]:
    mid = UUID(material_id)
    normalization = NormalizationService()
    extraction = EntityExtractionService()
    transcription = TranscriptionService(get_settings())
    outcome = "ok"

    with sync_session_scope() as session:
        material = session.get(Material, mid)
        if material is None:
            return {"status": "missing", "material_id": material_id}

        try:
            if material.material_type == MaterialType.AUDIO:
                material.status = ProcessingStatus.TRANSCRIBING
                session.flush()
                path = Path(material.audio_storage_key or "")
                audio_bytes = path.read_bytes() if path.is_file() else b""
                text = transcription.transcribe_sync(
                    audio_bytes=audio_bytes,
                    mime_type=material.mime_type,
                )
                material.raw_text = text

            material.status = ProcessingStatus.NORMALIZING
            session.flush()
            base_text = material.raw_text or ""
            normalized = normalization.normalize(base_text)
            material.normalized_text = normalized

            material.status = ProcessingStatus.EXTRACTING
            session.flush()
            session.execute(
                delete(MaterialExtractedEntity).where(MaterialExtractedEntity.material_id == material.id)
            )
            entities = extraction.extract(normalized)
            _upsert_entities_sync(session, material.id, entities)

            material.status = ProcessingStatus.DEDUPLICATING
            session.flush()
            _ensure_stub_insight_sync(session, material, normalized)

            material.status = ProcessingStatus.COMPLETED
            material.processing_error = None
            session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for material %s", material_id)
            material.status = ProcessingStatus.FAILED
            material.processing_error = str(exc)
            session.flush()
            outcome = "error"

    recompute_dashboard_aggregates.delay()
    return {"status": outcome, "material_id": material_id}


def _dashboard_upsert_sync(session: Session, kind: DashboardAggregateKind, period_key: str, payload: dict):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    insert_stmt = insert(DashboardAggregate).values(
        id=uuid.uuid4(),
        kind=kind,
        period_key=period_key,
        payload=payload,
        computed_at=now,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_dashboard_kind_period",
        set_={
            "payload": insert_stmt.excluded.payload,
            "computed_at": insert_stmt.excluded.computed_at,
        },
    )
    session.execute(upsert_stmt)


@celery_app.task(name="app.workers.tasks.pipeline.recompute_dashboard_aggregates")
def recompute_dashboard_aggregates() -> str:
    from datetime import datetime, timezone

    from sqlalchemy import func

    period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sync_session_scope() as session:
        m_total = session.scalar(select(func.count()).select_from(Material)) or 0
        rows = session.execute(
            select(Material.status, func.count()).group_by(Material.status)
        ).all()
        m_by_status = {str(k.value): int(v) for k, v in rows}
        i_total = session.scalar(select(func.count()).select_from(Insight)) or 0
        e_total = session.scalar(select(func.count()).select_from(MaterialExtractedEntity)) or 0

        _dashboard_upsert_sync(
            session,
            DashboardAggregateKind.MATERIAL_COUNTS,
            period,
            {"total": int(m_total), "by_status": m_by_status},
        )
        _dashboard_upsert_sync(
            session,
            DashboardAggregateKind.INSIGHT_COUNTS,
            period,
            {"total": int(i_total)},
        )
        _dashboard_upsert_sync(
            session,
            DashboardAggregateKind.ENTITY_FREQUENCY,
            period,
            {"total_entities": int(e_total)},
        )
        failed = m_by_status.get(ProcessingStatus.FAILED.value, 0)
        _dashboard_upsert_sync(
            session,
            DashboardAggregateKind.PIPELINE_HEALTH,
            period,
            {
                "failed_materials": failed,
                "failure_rate": (failed / m_total) if m_total else 0.0,
            },
        )
    return period
