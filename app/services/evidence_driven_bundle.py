"""Data-first helpers: dashboard snapshot, empty-state detection, evidence-shaped insights."""

from __future__ import annotations

import uuid
from typing import Any


def dashboard_first_bundle(ctx: dict[str, Any]) -> dict[str, Any]:
    """Compact dashboard block (always safe to return before LLM)."""
    sent = dict(ctx.get("sentiment") or {})
    pos = float(sent.get("positive_pct") or 0.0)
    neg = float(sent.get("negative_pct") or 0.0)
    neu = float(sent.get("neutralish_pct") or max(0.0, 100.0 - pos - neg))
    topics = ctx.get("topics_pie") or []
    problems = ctx.get("problems_bar") or []
    risks = ctx.get("risks_bar") or []
    return {
        "topics": [{"label": str(x.get("label") or ""), "count": int(x.get("value") or 0), "pct": float(x.get("pct") or 0.0)} for x in topics if isinstance(x, dict)][:20],
        "problems": [{"label": str(x.get("label") or ""), "count": int(x.get("value") or 0), "pct": float(x.get("pct") or 0.0)} for x in problems if isinstance(x, dict)][:20],
        "risks": [{"label": str(x.get("label") or ""), "count": int(x.get("value") or 0), "pct": float(x.get("pct") or 0.0)} for x in risks if isinstance(x, dict)][:20],
        "sentiment": {"positive_pct": pos, "negative_pct": neg, "neutral_pct": round(neu, 1)},
        "interview_count": int(ctx.get("interview_count") or 0),
    }


def _bar_nonempty(rows: Any) -> bool:
    if not isinstance(rows, list):
        return False
    return any(int((x or {}).get("value") or 0) > 0 for x in rows if isinstance(x, dict))


def dashboard_empty_for_llm(ctx: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    If True, skip LLM entirely (no abstract synthesis).

    Empty means: no interviews, or no entities and no distributional signal and <2 quotes.
    """
    missing: list[str] = []
    ic = int(ctx.get("interview_count") or 0)
    ent = int(ctx.get("entity_row_count") or 0)
    quotes = ctx.get("quotes") or []
    qn = len(quotes) if isinstance(quotes, list) else 0
    eq = int(ctx.get("evidence_quotes_count") if ctx.get("evidence_quotes_count") is not None else qn)

    if ic < 1:
        missing.append("мало интервью")
    if ent < 1:
        missing.append("нет извлечённых сущностей")
    if qn < 2 and eq < 2:
        missing.append("недостаточно цитат")

    topics_ok = _bar_nonempty(ctx.get("topics_pie"))
    prob_ok = _bar_nonempty(ctx.get("problems_bar"))
    risk_ok = _bar_nonempty(ctx.get("risks_bar"))
    if not topics_ok and not prob_ok and not risk_ok:
        missing.append("нет проблем/рисков/тем в агрегатах")

    empty = ic < 1 or (ent < 1 and not topics_ok and not prob_ok and not risk_ok) or (qn < 2 and eq < 2 and not topics_ok)
    return empty, list(dict.fromkeys(missing))


def insufficient_data_payload(lang: str, missing: list[str]) -> dict[str, Any]:
    lg = str(lang or "ru").strip().lower()[:8]
    msg = (
        "Недостаточно данных для вывода"
        if lg.startswith("ru")
        else ("Maʼlumot yetarli emas" if lg.startswith("uz") else "Insufficient data for synthesis")
    )
    return {"status": "insufficient_data", "message": msg, "missing": missing or ["unknown"]}


def insufficient_missing_from_readiness(
    *,
    strict_ready: bool,
    strict_checklist: list[Any],
    can_synthesize: bool,
) -> list[str]:
    """Human-readable `missing` entries when synthesis gates fail (anti-hallucination payload)."""
    missing: list[str] = []
    if not can_synthesize:
        missing.append("мало сигнала для синтеза")
    if not strict_ready:
        for x in strict_checklist or []:
            passed = bool(getattr(x, "passed", True))
            if passed:
                continue
            lab = str(getattr(x, "label", None) or getattr(x, "id", "") or "").strip()
            if lab:
                missing.append(lab)
    return list(dict.fromkeys(missing))


def pr_quality_warning(ctx: dict[str, Any]) -> str | None:
    """Warn when sample is small and PR bar signal is empty (spec §6)."""
    ic = int(ctx.get("interview_count") or 0)
    if ic >= 10:
        return None
    if _bar_nonempty(ctx.get("problems_bar")) or _bar_nonempty(ctx.get("risks_bar")):
        return None
    return "Недостаточно данных для качественного анализа"


def evidence_insights_from_grounding(
    pr_grounding: list[dict[str, Any]],
    *,
    interview_count: int,
) -> list[dict[str, Any]]:
    """Turn pr_grounding rows into API-shaped evidence insights (ids + coverage)."""
    ic = max(1, int(interview_count or 1))
    out: list[dict[str, Any]] = []
    for row in pr_grounding:
        if not isinstance(row, dict):
            continue
        insight = str(row.get("insight") or "").strip()
        ev = [x for x in (row.get("evidence") or []) if isinstance(x, dict)]
        if len(ev) < 2 or not insight:
            continue
        iid = str(row.get("insight_id") or uuid.uuid4())
        src_keys: set[str] = set()
        tr_ids: set[str] = set()
        shaped_ev: list[dict[str, Any]] = []
        for it in ev[:5]:
            quote = str(it.get("quote") or "")[:900]
            if len(quote) < 4:
                continue
            tid = str(it.get("transcript_id") or "")
            cid = str(it.get("chunk_id") or "")
            doc = str(it.get("source_document_id") or "")
            aud = str(it.get("source_audio_id") or "")
            seg = it.get("segment") if isinstance(it.get("segment"), dict) else {}
            shaped_ev.append(
                {
                    "quote": quote,
                    "transcript_id": tid,
                    "chunk_id": cid,
                    "segment": seg,
                    "source_document_id": doc or None,
                    "source_audio_id": aud or None,
                    "entity_id": str(it.get("entity_id") or "") or None,
                }
            )
            if doc:
                src_keys.add(f"doc:{doc}")
            if aud:
                src_keys.add(f"audio:{aud}")
            if tid:
                tr_ids.add(tid)
        if len(shaped_ev) < 2:
            continue
        cov_sources = len({*(src_keys), *(f"tr:{t}" for t in tr_ids)})
        coverage_pct = min(100.0, round(100.0 * cov_sources / ic, 1))
        count = max(len(shaped_ev), cov_sources)
        out.append(
            {
                "insight_id": iid,
                "insight": insight[:2000],
                "count": count,
                "coverage_pct": coverage_pct,
                "sentiment": "",
                "evidence": shaped_ev,
                "source_ids": sorted(src_keys)[:32],
                "transcript_ids": sorted(tr_ids)[:32],
            }
        )
    return out


def attach_based_on_to_actions(
    action_cards: list[dict[str, Any]],
    evidence_insights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Link each action card to insight_ids via overlapping entity/source ids."""
    out: list[dict[str, Any]] = []
    for c in action_cards:
        if not isinstance(c, dict):
            continue
        refs = c.get("evidence_refs") if isinstance(c.get("evidence_refs"), list) else []
        ref_ids = {str((x or {}).get("entity_id") or "") for x in refs if isinstance(x, dict)}
        ref_ids.discard("")
        based: list[str] = []
        for ins in evidence_insights:
            if not isinstance(ins, dict):
                continue
            iid = str(ins.get("insight_id") or "")
            hit = False
            for ev in ins.get("evidence") or []:
                if not isinstance(ev, dict):
                    continue
                eid = str(ev.get("entity_id") or "")
                if eid and eid in ref_ids:
                    hit = True
                    break
            if hit and iid:
                based.append(iid)
            if len(based) >= 5:
                break
        nc = dict(c)
        nc["based_on"] = based
        out.append(nc)
    return out
