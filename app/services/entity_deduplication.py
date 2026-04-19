"""Deterministic grouping of `ExtractedEntity` rows; sets `canonical_entity_id`."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import EntityType
from app.models.extracted_entity import ExtractedEntity


def normalize_fingerprint_text(value: str) -> str:
    s = unicodedata.normalize("NFC", value or "")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s[:480]


def entity_fingerprint(entity_type: EntityType, title: str, content: str) -> str:
    """Stable key: same type + normalized title + normalized content prefix."""
    nt = normalize_fingerprint_text(title)
    nc = normalize_fingerprint_text(content[:800])
    return f"{entity_type.value}|{nt}|{nc}"


def deduplicate_project_entities_sync(session: Session, project_id: UUID) -> dict:
    """
    Clear prior links, regroup by fingerprint, link duplicates to earliest row (canonical).
    Returns stats for logging / payloads.
    """
    entities = list(
        session.scalars(
            select(ExtractedEntity)
            .where(ExtractedEntity.project_id == project_id)
            .order_by(ExtractedEntity.created_at.asc(), ExtractedEntity.id.asc())
        ).all()
    )

    for e in entities:
        e.canonical_entity_id = None
    session.flush()

    groups: dict[str, list[ExtractedEntity]] = defaultdict(list)
    for e in entities:
        fp = entity_fingerprint(e.entity_type, e.title, e.content)
        groups[fp].append(e)

    clusters_merged = 0
    duplicates_linked = 0
    for g in groups.values():
        if len(g) <= 1:
            continue
        clusters_merged += 1
        root = g[0]
        for dup in g[1:]:
            dup.canonical_entity_id = root.id
            duplicates_linked += 1

    session.flush()
    return {
        "total_entities": len(entities),
        "distinct_fingerprints": len(groups),
        "clusters_merged": clusters_merged,
        "duplicates_linked": duplicates_linked,
    }
