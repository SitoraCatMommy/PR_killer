"""Assemble ready-to-use report modes from cached LLM + dashboard (no new analytics)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.settings import Settings, get_settings
from app.models.research_batch import ResearchBatch
from app.schemas.scenario_report import (
    AudienceInsightScenarioSection,
    BatchScenarioReportResponse,
    MessagingKitScenarioSection,
    PRAuditScenarioSection,
    ReportMode,
)
from app.services.audience_portrait_service import build_portrait_context
from app.services.batch_cached_llm_service import (
    get_or_create_audience_portrait_response,
    get_or_create_pr_strategy_response,
)
from app.services.research_batch_dashboard_service import build_batch_dashboard


def _risks_from_ctx_and_strategy(ctx: dict[str, Any], reputational_risks: list[str]) -> list[str]:
    risks: list[str] = []
    for r in ctx.get("risks_bar") or []:
        lab = str((r or {}).get("label") or "").strip()
        if lab:
            risks.append(lab)
    risks.extend([x for x in reputational_risks if x.strip()])
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for x in risks:
        k = x.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
    return out[:40]


def _recommendations_from_strategy(key_pr_insights: list[str], recommended_messages: list[str]) -> list[str]:
    recs: list[str] = []
    recs.extend([x for x in key_pr_insights if x.strip()][:12])
    recs.extend([x for x in recommended_messages if x.strip()][:12])
    seen: set[str] = set()
    out: list[str] = []
    for x in recs:
        k = x.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
    return out[:28]


def _audience_phrases_from_ctx(ctx: dict[str, Any]) -> list[str]:
    phrases: list[str] = []
    for q in (ctx.get("quotes") or [])[:22]:
        if not isinstance(q, dict):
            continue
        t = str(q.get("text") or "").strip()
        if len(t) < 14:
            continue
        phrases.append(t[:280])
    if len(phrases) < 6:
        for ins in (ctx.get("top_insights") or [])[:14]:
            if not isinstance(ins, dict):
                continue
            t = str(ins.get("text") or "").strip()
            if len(t) < 14:
                continue
            phrases.append(t[:280])
    # de-dupe
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        k = p.lower()[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out[:24]


async def build_batch_scenario_report(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    mode: ReportMode,
    output_language: str,
    recalculate: bool = False,
    settings: Settings | None = None,
) -> BatchScenarioReportResponse:
    _ = recalculate
    st = settings or get_settings()
    lang = (output_language or "ru").strip().lower()[:8]
    if lang not in {"ru", "uz", "en"}:
        lang = "ru"

    base_meta: dict[str, Any] = {
        "output_language": lang,
        "mode": mode,
        "source_mode": "derived_view",
        "derived_from_cache": True,
    }

    if mode == "pr_audit":
        ctx = await build_portrait_context(session, batch, group_by=None, segment_value=None)
        portrait_resp = await get_or_create_audience_portrait_response(
            session,
            batch,
            group_by=None,
            segment_value=None,
            output_language=lang,
            recalculate=False,
            settings=st,
        )
        strategy = await get_or_create_pr_strategy_response(
            session,
            batch,
            group_by=None,
            segment_value=None,
            output_language=lang,
            recalculate=False,
            settings=st,
            prefetched_context=ctx,
            prefetched_portrait=portrait_resp.portrait.model_dump(),
        )
        risks = _risks_from_ctx_and_strategy(ctx, list(strategy.reputational_risks))
        recs = _recommendations_from_strategy(
            list(strategy.key_pr_insights),
            list(strategy.recommended_messages),
        )
        section = PRAuditScenarioSection(
            brand_perception_summary=strategy.brand_perception_summary or "",
            risks=risks,
            communication_gaps=list(strategy.communication_gaps),
            recommendations=recs,
            priority_actions=list(strategy.priority_actions),
        )
        base_meta["interview_count"] = int(ctx.get("interview_count") or 0)
        return BatchScenarioReportResponse(
            mode=mode,
            batch_id=batch.id,
            meta=base_meta,
            pr_audit=section,
            audience_insight=None,
            messaging_kit=None,
        )

    if mode == "audience":
        ctx = await build_portrait_context(session, batch, group_by=None, segment_value=None)
        portrait_resp = await get_or_create_audience_portrait_response(
            session,
            batch,
            group_by=None,
            segment_value=None,
            output_language=lang,
            recalculate=False,
            settings=st,
        )
        dash = await build_batch_dashboard(session, batch, group_by=None)
        snap = dash.get("audience_snapshot") if isinstance(dash.get("audience_snapshot"), dict) else {}
        patterns = dash.get("top_patterns") or []
        wf = dash.get("word_frequency") or []
        section = AudienceInsightScenarioSection(
            portrait=portrait_resp.portrait,
            confidence=portrait_resp.confidence,
            interview_count=int(ctx.get("interview_count") or portrait_resp.interview_count or 0),
            audience_snapshot=dict(snap),
            top_patterns=list(patterns) if isinstance(patterns, list) else [],
            word_frequency=list(wf) if isinstance(wf, list) else [],
        )
        base_meta["interview_count"] = section.interview_count
        return BatchScenarioReportResponse(
            mode=mode,
            batch_id=batch.id,
            meta=base_meta,
            pr_audit=None,
            audience_insight=section,
            messaging_kit=None,
        )

    # messaging
    ctx = await build_portrait_context(session, batch, group_by=None, segment_value=None)
    portrait = await get_or_create_audience_portrait_response(
        session,
        batch,
        group_by=None,
        segment_value=None,
        output_language=lang,
        recalculate=False,
        settings=st,
    )
    strategy = await get_or_create_pr_strategy_response(
        session,
        batch,
        group_by=None,
        segment_value=None,
        output_language=lang,
        recalculate=False,
        settings=st,
        prefetched_context=ctx,
        prefetched_portrait=portrait.portrait.model_dump(),
    )
    phrases = _audience_phrases_from_ctx(ctx)
    section = MessagingKitScenarioSection(
        talking_points=list(strategy.talking_points),
        recommended_messages=list(strategy.recommended_messages),
        audience_phrases=phrases,
        media_hooks=list(strategy.media_hooks),
    )
    base_meta["interview_count"] = int(ctx.get("interview_count") or 0)
    return BatchScenarioReportResponse(
        mode=mode,
        batch_id=batch.id,
        meta=base_meta,
        pr_audit=None,
        audience_insight=None,
        messaging_kit=section,
    )
