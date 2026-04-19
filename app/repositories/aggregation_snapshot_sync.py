"""Sync upsert for `AggregationSnapshot` (Celery / psycopg)."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.aggregation_snapshot import AggregationSnapshot


def upsert_aggregation_snapshot_sync(
    session: Session,
    *,
    project_id: UUID,
    snapshot_type: str,
    period_key: str,
    payload_json: dict[str, Any],
) -> AggregationSnapshot:
    ins = insert(AggregationSnapshot).values(
        id=uuid.uuid4(),
        project_id=project_id,
        snapshot_type=snapshot_type,
        period_key=period_key,
        payload_json=payload_json,
    )
    stmt = ins.on_conflict_do_update(
        constraint="uq_aggregation_snapshots_project_type_period",
        set_={
            "payload_json": ins.excluded.payload_json,
            "created_at": func.now(),
        },
    ).returning(AggregationSnapshot)

    row = session.execute(stmt).scalar_one()
    session.flush()
    return row
