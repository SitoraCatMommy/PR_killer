"""CustDev PR analyst extras: insight graph, narrative stubs, trend heuristics (deterministic + strategy hooks)."""

from __future__ import annotations

from typing import Any

from app.schemas.research_batch import AudiencePortraitResponse, PRStrategyResponse
from app.services.pr_grounding_service import _pick_evidence_for_text


def build_insight_graph_v1(ctx: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for row in (ctx.get("problems_bar") or [])[:14]:
        if isinstance(row, dict):
            nodes.append(
                {
                    "kind": "pain_point",
                    "label": str(row.get("label") or ""),
                    "frequency": int(row.get("value") or 0),
                    "evidence_quotes": [],
                    "confidence": 0.55,
                    "segments": [],
                }
            )
    for row in (ctx.get("risks_bar") or [])[:10]:
        if isinstance(row, dict):
            nodes.append(
                {
                    "kind": "fear_or_risk",
                    "label": str(row.get("label") or ""),
                    "frequency": int(row.get("value") or 0),
                    "evidence_quotes": [],
                    "confidence": 0.52,
                    "segments": [],
                }
            )
    for row in (ctx.get("top_patterns") or [])[:10]:
        if isinstance(row, dict):
            nodes.append(
                {
                    "kind": "behavior_pattern",
                    "label": str(row.get("text") or ""),
                    "frequency": int(row.get("count") or 0),
                    "evidence_quotes": [],
                    "confidence": 0.5,
                    "segments": [],
                }
            )
    for row in (ctx.get("top_insights") or [])[:12]:
        if isinstance(row, dict):
            kind = str(row.get("pr_signal_type") or row.get("type") or "insight")
            nodes.append(
                {
                    "kind": kind,
                    "label": str(row.get("text") or "")[:400],
                    "frequency": 1,
                    "evidence_quotes": [],
                    "confidence": 0.48,
                    "segments": [],
                }
            )
    return {"schema": "insight_graph_v1", "nodes": nodes, "edges": []}


def build_hierarchical_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    topics = ctx.get("topics_pie") or []
    theme_line = ", ".join(str(x.get("label") or "") for x in topics[:10] if isinstance(x, dict))
    ins = ctx.get("top_insights") or []
    batch_line = ""
    if ins and isinstance(ins[0], dict):
        batch_line = str(ins[0].get("text") or "")[:800]
    return {
        "unit_level": f"Detected {int(ctx.get('interview_count') or 0)} interview units in evidence scope.",
        "theme_level": theme_line[:2000] or "—",
        "batch_level": batch_line or "—",
    }


def build_pr_risk_alerts(strategy: PRStrategyResponse, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Legacy flat list (kept for older clients). Prefer ``build_pr_risk_alerts_v2``."""
    out: list[dict[str, Any]] = []
    for row in build_pr_risk_alerts_v2(strategy, ctx):
        out.append(
            {
                "risk_index": row.get("risk_index"),
                "severity": row.get("severity"),
                "title": row.get("title"),
                "evidence": [e.get("quote", "") for e in (row.get("evidence_refs") or []) if isinstance(e, dict)],
                "trend_delta": row.get("trend"),
            }
        )
    return out[:12]


def build_pr_risk_alerts_v2(strategy: PRStrategyResponse, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """risk_index 0–100, severity, trend (up/down/stable), evidence_refs (2–4 quotes when possible)."""
    quotes: list[dict[str, Any]] = [q for q in (ctx.get("quotes") or []) if isinstance(q, dict)]
    out: list[dict[str, Any]] = []
    risks = ctx.get("risks_bar") or []
    prev = None
    for i, row in enumerate(risks[:8]):
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        v = int(row.get("value") or 0)
        idx = min(100, int(18 + v * 4 + (len(risks) - i) * 2))
        sev: str = "high" if v >= 6 else ("medium" if v >= 3 else "low")
        trend = "stable"
        if prev is not None:
            trend = "up" if v > prev else ("down" if v < prev else "stable")
        prev = v
        ev_objs = _pick_evidence_for_text(label, quotes, min_n=1, max_n=4)
        out.append(
            {
                "risk_index": idx,
                "severity": sev,
                "trend": trend,
                "title": label[:400],
                "evidence_refs": ev_objs,
            }
        )
    for a in (strategy.alerts or [])[:6]:
        ev_objs = _pick_evidence_for_text(a.message, quotes, min_n=1, max_n=4)
        out.append(
            {
                "risk_index": 52 if a.severity == "medium" else 72,
                "severity": str(a.severity),
                "trend": "stable",
                "title": a.message[:400],
                "evidence_refs": ev_objs,
            }
        )
    return out[:14]


def build_message_lab(strategy: PRStrategyResponse) -> dict[str, Any]:
    """Heuristic preview from action cards (interactive POST endpoint does full LLM)."""
    cards = strategy.action_cards or []
    msgs = [c.message for c in cards if str(c.message).strip()][:8]
    if not msgs:
        msgs = [m for m in (strategy.recommended_messages or []) if str(m).strip()][:6]
    scored = []
    for i, m in enumerate(msgs):
        base = 0.58 + (i % 5) * 0.04
        st = "ok" if cards and i < len(cards) and cards[i].evidence_status == "ok" else "mixed"
        scored.append(
            {
                "original": m,
                "clarity_score": round(min(0.95, base), 2),
                "trust_score": round(min(0.95, base + 0.05), 2),
                "risk_score": round(max(0.08, 0.42 - i * 0.02), 2),
                "rewrite_variants": [
                    (m[:160] + " — уточнить формулировку под сегмент.") if len(m) > 30 else m,
                    (m[:160] + " — добавить конкретный факт из интервью.") if len(m) > 30 else m,
                ][:2],
                "segment_reactions": [{"segment": "all", "reaction": "Heuristic placeholder; use Message Lab POST."}],
                "evidence_status": st,
            }
        )
    return {"items": scored}


def build_narrative_builder(strategy: PRStrategyResponse, portrait: AudiencePortraitResponse) -> dict[str, Any]:
    stmt = (strategy.brand_perception_summary or portrait.portrait.brand_perception or "").strip()[:600]
    faq = []
    for x in (strategy.key_pr_insights or [])[:5]:
        xs = str(x).strip()
        if xs:
            faq.append({"q": "What do respondents signal here?", "a": xs[:400]})
    return {
        "statement": stmt,
        "qa": faq,
        "faq": faq,
        "key_messages": [x for x in strategy.recommended_messages if str(x).strip()][:12],
        "do_dont": {
            "do": [x for x in strategy.talking_points if str(x).strip()][:8],
            "dont": [x for x in strategy.communication_gaps if str(x).strip()][:8],
        },
        "proof_points": [x for x in strategy.media_hooks if str(x).strip()][:8],
    }


def build_trend_dashboard(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Trend UI: **only** buckets from ``timeline_series_real`` (weekly bins from interview metadata dates
    or entity created_at). No heuristic time series when dates are missing.
    """
    tl = ctx.get("timeline_series_real")
    if not isinstance(tl, dict):
        tl = {}
    raw_series = [x for x in (tl.get("series") or []) if isinstance(x, dict)]
    if not raw_series:
        note = str(
            tl.get("note")
            or "Нет временного ряда: в метаданных интервью не найдено дат для недельных корзин."
        )
        return {
            "series": [],
            "emerging_themes": [],
            "fading_themes": [],
            "notes": note,
            "diagnostics": "empty_timeline",
        }

    max_risk = max((int(x.get("risk_volume") or 0) for x in raw_series), default=0) or 1
    series: list[dict[str, Any]] = []
    for s in raw_series:
        ss, ri = s.get("sentiment_score"), s.get("risk_index")
        if ss is not None and ri is not None:
            sentiment_score = int(ss)
            risk_index = int(ri)
        else:
            pos = int(s.get("positive_signals") or 0)
            neg = int(s.get("negative_signals") or 0)
            tot = pos + neg or 1
            bal = int(s.get("sentiment_balance") or (pos - neg))
            sentiment_score = int(max(0, min(100, round(50.0 + 50.0 * bal / tot))))
            rv = int(s.get("risk_volume") or 0)
            risk_index = int(max(0, min(100, round(100.0 * rv / max_risk))))
        series.append(
            {
                "period": str(s.get("period") or ""),
                "sentiment_score": sentiment_score,
                "risk_index": risk_index,
                "theme_volume": int(s.get("theme_volume") or 0),
            }
        )
    return {
        "series": series,
        "emerging_themes": [str(x) for x in (tl.get("emerging") or [])[:8] if str(x).strip()],
        "fading_themes": [str(x) for x in (tl.get("fading") or [])[:8] if str(x).strip()],
        "notes": str(
            tl.get("note")
            or "Недельные корзины по дате из metadata (date) или по дате создания сущности."
        ),
        "diagnostics": None,
    }


def build_custdev_bundle(
    ctx: dict[str, Any],
    *,
    portrait: AudiencePortraitResponse,
    strategy: PRStrategyResponse,
) -> dict[str, Any]:
    return {
        "insight_graph": build_insight_graph_v1(ctx),
        "hierarchical_summary": build_hierarchical_summary(ctx),
        "pr_risk_alerts": build_pr_risk_alerts(strategy, ctx),
        "pr_risk_alerts_v2": build_pr_risk_alerts_v2(strategy, ctx),
        "message_lab": build_message_lab(strategy),
        "narrative_builder": build_narrative_builder(strategy, portrait),
        "trend_dashboard": build_trend_dashboard(ctx),
    }
