"""Build `ResearchSummary` from canonical entities + aggregation snapshot (no LLM)."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import EntityType, SummaryStatus
from app.domain.research_constants import PERIOD_KEY_ALL_TIME, SNAPSHOT_TYPE_RESEARCH_ENTITIES
from app.models.aggregation_snapshot import AggregationSnapshot
from app.models.extracted_entity import ExtractedEntity
from app.models.project import Project
from app.models.research_summary import ResearchSummary

logger = logging.getLogger(__name__)


def _entity_item(e: ExtractedEntity) -> dict[str, Any]:
    ev = e.evidence_json if isinstance(e.evidence_json, dict) else {}
    quote = ev.get("quote") if isinstance(ev.get("quote"), str) else None
    return {
        "entity_id": str(e.id),
        "entity_type": e.entity_type.value,
        "title": e.title,
        "content": e.content,
        "confidence_score": e.confidence_score,
        "chunk_id": str(e.chunk_id),
        "evidence_quote": quote,
    }


class SummaryService:
    """Deterministic summary sections referencing real `ExtractedEntity` rows only.

    Satisfies `ResearchSummaryProvider` (see `app.services.summary.provider`) structurally.
    """

    def _load_snapshot(self, session: Session, project_id: UUID) -> dict[str, Any] | None:
        row = session.scalar(
            select(AggregationSnapshot)
            .where(
                AggregationSnapshot.project_id == project_id,
                AggregationSnapshot.snapshot_type == SNAPSHOT_TYPE_RESEARCH_ENTITIES,
                AggregationSnapshot.period_key == PERIOD_KEY_ALL_TIME,
            )
            .order_by(AggregationSnapshot.created_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return dict(row.payload_json or {})

    def generate_project_summary_sync(self, session: Session, project_id: UUID) -> ResearchSummary:
        if session.get(Project, project_id) is None:
            raise ValueError("project_not_found")

        snapshot = self._load_snapshot(session, project_id) or {}

        canonicals = list(
            session.scalars(
                select(ExtractedEntity)
                .where(
                    ExtractedEntity.project_id == project_id,
                    ExtractedEntity.canonical_entity_id.is_(None),
                )
                .order_by(ExtractedEntity.entity_type, ExtractedEntity.title, ExtractedEntity.id)
            ).all()
        )

        key_findings: list[dict[str, Any]] = []
        facts: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        opportunities: list[dict[str, Any]] = []
        recommendations: list[dict[str, Any]] = []
        open_questions: list[dict[str, Any]] = []

        problem_like = {
            EntityType.PROBLEM,
            EntityType.PAIN_POINT,
            EntityType.USER_NEED,
            EntityType.TRUST_ISSUE,
            EntityType.ADOPTION_BARRIER,
        }
        fact_like = {
            EntityType.SUPPORTING_FACT,
            EntityType.SENTIMENT_SIGNAL,
            EntityType.BEHAVIOR_PATTERN,
            EntityType.CLAIM,
            EntityType.METRIC,
            EntityType.DATE,
            EntityType.PERSON,
            EntityType.ORGANIZATION,
            EntityType.LOCATION,
            EntityType.TOPIC,
            EntityType.REFERENCE,
        }

        for e in canonicals:
            item = _entity_item(e)
            et = e.entity_type
            cl = (e.content or "").lower()

            if et == EntityType.RECOMMENDATION:
                recommendations.append(item)
            elif et == EntityType.CLAIM and "recommend" in cl:
                recommendations.append({**item, "источник": "ключевое слово в формулировке утверждения"})
            elif et == EntityType.CUSTOM:
                recommendations.append(item)
            elif et in problem_like:
                key_findings.append({**item, "источник": "тема проблемы или потребности"})
            elif et in fact_like:
                facts.append(item)
            elif et == EntityType.HYPOTHESIS:
                hypotheses.append(item)
            elif et == EntityType.RISK:
                risks.append(item)
            elif et == EntityType.OPPORTUNITY:
                opportunities.append(item)
            elif et == EntityType.OPEN_QUESTION:
                open_questions.append(item)

            if (e.confidence_score is None or e.confidence_score < 0.68) and et != EntityType.OPEN_QUESTION:
                open_questions.append({**item, "причина": "низкая или отсутствующая уверенность модели"})

        totals = snapshot.get("totals") or {}
        snapshot_nc = totals.get("canonical_entities")
        live_nc = len(canonicals)
        # Stale snapshot: aggregate ran before extract (or before re-aggregate) can store
        # canonical_entities=0. dict.get("canonical_entities", live_nc) still returns 0 because
        # the key exists — so we must prefer the live canonical count for the header.
        if snapshot_nc is not None and snapshot_nc != live_nc:
            logger.info(
                "SummaryService project_id=%s snapshot canonical_entities=%s != live=%s; "
                "using live count and recomputing type distribution when snapshot is empty",
                project_id,
                snapshot_nc,
                live_nc,
            )

        nc = live_nc
        td: dict[str, int] = dict(snapshot.get("entity_type_distribution") or {})
        if not td and canonicals:
            td = dict(Counter(c.entity_type.value for c in canonicals))

        logger.info(
            "SummaryService project_id=%s live_canonical_entities=%s snapshot_present=%s",
            project_id,
            live_nc,
            bool(snapshot),
        )

        summary_lines = [
            f"Канонических единиц исследования: {nc}.",
            f"Распределение по типам: {td}." if td else "Нет распределения по типам (сначала запустите сбор аналитики).",
            "Ниже перечислены только реально сохранённые единицы (идентификаторы и привязка к фрагментам текста).",
        ]
        summary_text = "\n".join(summary_lines)

        row = ResearchSummary(
            project_id=project_id,
            status=SummaryStatus.READY,
            summary_text=summary_text,
            key_findings_json=key_findings,
            facts_json=facts,
            hypotheses_json=hypotheses,
            risks_json=risks,
            opportunities_json=opportunities,
            recommendations_json=recommendations,
            open_questions_json=open_questions,
        )
        session.add(row)
        session.flush()
        return row
