"""Attach 2–5 entity-backed quotes to each PR insight / risk / message (data-first, no fabrication)."""

from __future__ import annotations

import re
import uuid
from typing import Any

_TOKEN = re.compile(r"[\wа-яёА-ЯЁ]+", re.UNICODE)


def _tok(s: str) -> set[str]:
    return {w.lower() for w in _TOKEN.findall(s) if len(w) > 2}


def _quote_evidence_item(q: dict[str, Any]) -> dict[str, Any]:
    seg = q.get("segment") if isinstance(q.get("segment"), dict) else {}
    return {
        "quote": str(q.get("text") or "")[:900],
        "entity_id": q.get("entity_id"),
        "source_document_id": q.get("source_document_id"),
        "source_audio_id": q.get("source_audio_id"),
        "transcript_id": q.get("transcript_id"),
        "chunk_id": q.get("chunk_id"),
        "segment": seg,
    }


def _score_match(insight: str, quote: dict[str, Any]) -> float:
    t_ins = _tok(insight)
    t_q = _tok(str(quote.get("text") or "")) | _tok(str(quote.get("title") or ""))
    if not t_ins or not t_q:
        return 0.0
    inter = len(t_ins & t_q)
    if inter < 1:
        return 0.0
    union = len(t_ins | t_q) or 1
    j = inter / union
    if str(quote.get("text") or "").lower() in insight.lower():
        j += 0.15
    return min(1.0, j)


def _pick_evidence_for_text(
    text: str,
    quotes: list[dict[str, Any]],
    *,
    min_n: int = 2,
    max_n: int = 5,
) -> list[dict[str, Any]]:
    t = (text or "").strip()
    if len(t) < 4 or not quotes:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for q in quotes:
        if not isinstance(q, dict):
            continue
        body = str(q.get("text") or "").strip()
        if len(body) < 10:
            continue
        s = _score_match(t, q)
        if s < 0.01:
            continue
        scored.append((s, q))
    scored.sort(key=lambda x: -x[0])
    out: list[dict[str, Any]] = []
    used_entity: set[str] = set()
    for _s, q in scored:
        eid = str(q.get("entity_id") or "")
        if eid and eid in used_entity:
            continue
        if eid:
            used_entity.add(eid)
        out.append(_quote_evidence_item(q))
        if len(out) >= max_n:
            break
    if len(out) < min_n:
        return []
    return out


def enrich_action_cards_with_evidence(
    action_cards: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach 2–5 grounded quotes per card; mark insufficient_evidence when <2."""
    out: list[dict[str, Any]] = []
    for raw in action_cards:
        if not isinstance(raw, dict):
            continue
        msg = str(raw.get("message") or raw.get("action") or "").strip()
        ev = _pick_evidence_for_text(msg, quotes, min_n=2, max_n=5) if msg else []
        st = "ok" if len(ev) >= 2 else "insufficient_evidence"
        bo = raw.get("based_on") if isinstance(raw.get("based_on"), list) else []
        based_on = [str(x).strip() for x in bo if str(x).strip()][:24]
        out.append(
            {
                "action": str(raw.get("action") or "").strip()[:900],
                "for_segment": str(raw.get("for_segment") or "all")[:200],
                "channel": str(raw.get("channel") or "").strip()[:200],
                "message": str(raw.get("message") or "").strip()[:900],
                "expected_effect": str(raw.get("expected_effect") or "").strip()[:600],
                "risk_if_ignored": str(raw.get("risk_if_ignored") or "").strip()[:600],
                "evidence_refs": ev if st == "ok" else [],
                "evidence_status": st,
                "based_on": based_on,
            }
        )
    return out


def build_pr_grounding(
    strategy: dict[str, Any],
    quotes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For key_pr_insights, reputational_risks, recommended_messages — add rows
    with 2..5 real quotes each; omit if fewer than 2 (no low-evidence rows in output).
    """
    rows: list[dict[str, Any]] = []
    blocks: list[tuple[str, str, str]] = [
        ("key_pr_insight", "key_pr_insights", "key_pr_insight"),
        ("reputational_risk", "reputational_risks", "reputational_risk"),
        ("recommended_message", "recommended_messages", "recommended_message"),
    ]
    for public_kind, field, internal_kind in blocks:
        for text in (strategy.get(field) or []):
            t = str(text or "").strip()
            if not t:
                continue
            ev = _pick_evidence_for_text(t, quotes, min_n=2, max_n=5)
            if len(ev) < 2:
                continue
            rows.append(
                {
                    "insight_id": str(uuid.uuid4()),
                    "insight": t[:2000],
                    "insight_kind": internal_kind,
                    "insight_type": public_kind,
                    "evidence": ev,
                }
            )
    return rows
