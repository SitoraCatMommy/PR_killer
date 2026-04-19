"""Research domain: deduplicate entities, build dashboard-style aggregation snapshot."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.research_constants import PERIOD_KEY_ALL_TIME, SNAPSHOT_TYPE_RESEARCH_ENTITIES
from app.models.extracted_entity import ExtractedEntity
from app.repositories.aggregation_snapshot_sync import upsert_aggregation_snapshot_sync
from app.services.entity_deduplication import deduplicate_project_entities_sync


def _confidence_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    lo = int(score * 10) / 10.0
    hi = round(lo + 0.1, 1)
    return f"{lo:.1f}-{hi:.1f}"


class ResearchAggregationService:
    """Deduplicate `ExtractedEntity` rows and persist `AggregationSnapshot` payload."""

    def aggregate_project_sync(self, session: Session, project_id: UUID) -> dict[str, Any]:
        dedup_stats = deduplicate_project_entities_sync(session, project_id)

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

        type_dist: dict[str, int] = Counter(c.entity_type.value for c in canonicals)

        tag_counter: Counter[str] = Counter()
        for c in canonicals:
            tags = c.tags_json if isinstance(c.tags_json, dict) else {}
            for k, v in tags.items():
                key = f"{k}:{v}" if v is not None else str(k)
                tag_counter[key] += 1

        conf_buckets: Counter[str] = Counter()
        for c in canonicals:
            conf_buckets[_confidence_bucket(c.confidence_score)] += 1

        cluster_sizes: dict[UUID, int] = {}
        for root in canonicals:
            n = session.scalar(
                select(func.count())
                .select_from(ExtractedEntity)
                .where(
                    or_(
                        ExtractedEntity.id == root.id,
                        ExtractedEntity.canonical_entity_id == root.id,
                    )
                )
            )
            cluster_sizes[root.id] = int(n or 0)

        top_insights: list[dict[str, Any]] = []
        for root in sorted(
            canonicals,
            key=lambda r: (-cluster_sizes.get(r.id, 1), r.entity_type.value, r.title),
        )[:25]:
            members = session.scalars(
                select(ExtractedEntity.id).where(
                    or_(
                        ExtractedEntity.id == root.id,
                        ExtractedEntity.canonical_entity_id == root.id,
                    )
                )
            ).all()
            top_insights.append(
                {
                    "canonical_entity_id": str(root.id),
                    "entity_type": root.entity_type.value,
                    "title": root.title,
                    "cluster_size": cluster_sizes.get(root.id, 1),
                    "member_entity_ids": [str(mid) for mid in members],
                    "chunk_id": str(root.chunk_id),
                }
            )

        time_buckets: dict[str, int] = defaultdict(int)
        for c in canonicals:
            key = c.created_at.strftime("%Y-%m") if c.created_at else "unknown"
            time_buckets[key] += 1

        payload: dict[str, Any] = {
            "entity_type_distribution": dict(sorted(type_dist.items())),
            "tag_counts": dict(tag_counter.most_common(200)),
            "confidence_distribution": dict(sorted(conf_buckets.items())),
            "top_recurring_insights": top_insights,
            "time_buckets_monthly": dict(sorted(time_buckets.items())),
            "totals": {
                "canonical_entities": len(canonicals),
                "total_entity_rows": dedup_stats["total_entities"],
                "distinct_fingerprints": dedup_stats["distinct_fingerprints"],
                "clusters_merged": dedup_stats["clusters_merged"],
                "duplicates_linked": dedup_stats["duplicates_linked"],
            },
        }

        upsert_aggregation_snapshot_sync(
            session,
            project_id=project_id,
            snapshot_type=SNAPSHOT_TYPE_RESEARCH_ENTITIES,
            period_key=PERIOD_KEY_ALL_TIME,
            payload_json=payload,
        )
        return payload
