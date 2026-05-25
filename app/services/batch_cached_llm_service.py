"""DB-backed cache + orchestration for batch LLM endpoints (portrait, PR strategy, full report)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ReportStatus
from app.infrastructure.settings import Settings, get_settings
from app.models.research_batch import ResearchBatch
from app.repositories.batch_llm_cache_repository import BatchLlmCacheRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.schemas.decision_layer import DecisionAlertItem, ImpactEffortMatrixItem, PriorityActionItem
from app.schemas.research_batch import (
    AudiencePortraitFields,
    AudiencePortraitResponse,
    EvidenceDrivenInsight,
    FullReportResponse,
    InsufficientDataPayload,
    PRActionCardItem,
    PRGroundingRow,
    PRRiskAlertItem,
    PRStrategyResponse,
    SampleQuoteItem,
)
from app.services.data_readiness_service import insufficient_synthesis_message
from app.services.explainability_service import explainability_bundle
from app.services.decision_layer_service import build_impact_effort_matrix, parse_alerts, parse_priority_actions
from app.services.audience_portrait_service import build_portrait_context, generate_audience_portrait
from app.services.custdev_report_bundle import build_custdev_bundle, build_pr_risk_alerts_v2
from app.services.evidence_driven_bundle import dashboard_first_bundle, evidence_insights_from_grounding
from app.services.pr_strategy_service import generate_pr_strategy

logger = logging.getLogger(__name__)

CACHE_KIND_PORTRAIT = "audience_portrait"
CACHE_KIND_STRATEGY = "pr_strategy"


def make_cache_key(
    kind: str,
    batch_id: UUID,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    *,
    multi_interview_mode: bool | None = None,
) -> str:
    gb = (group_by or "").strip() or "_"
    sv = (segment_value or "").strip() or "_"
    lg = (output_language or "ru").strip().lower()[:8]
    mi = "sf_" if multi_interview_mode is None else ("sf1" if multi_interview_mode else "sf0")
    raw = f"{kind}:{batch_id}:{gb}:{sv}:{lg}:{mi}"
    if len(raw) > 720:
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{kind}:{batch_id}:h:{h}"
    return raw


def confidence_from_context(ctx: dict[str, Any]) -> tuple[float, int, dict[str, Any]]:
    """Heuristic 0..1 confidence from interview volume and signal density."""
    ic = int(ctx.get("interview_count") or 0)
    snap = ctx.get("audience_snapshot")
    if not isinstance(snap, dict):
        snap = {}
    nq = len(ctx.get("quotes") or [])
    nt = len(ctx.get("topics_pie") or [])
    ni = len(ctx.get("top_insights") or [])
    parts = (
        min(1.0, ic / 15.0) * 0.25,
        min(1.0, nq / 18.0) * 0.25,
        min(1.0, nt / 10.0) * 0.25,
        min(1.0, ni / 14.0) * 0.25,
    )
    conf = round(min(1.0, sum(parts)), 2)
    seg: dict[str, Any] = {k: v for k, v in snap.items() if k != "interview_count"}
    return conf, ic, seg


def _portrait_response(
    portrait: dict[str, str],
    meta: dict[str, Any],
    ctx: dict[str, Any],
    *,
    cache_hit: bool,
) -> AudiencePortraitResponse:
    conf, ic, seg = confidence_from_context(ctx)
    meta_out = {**meta, "cache_hit": cache_hit}
    dc = float(meta.get("data_coverage_score", conf))
    ex = explainability_bundle(ctx)
    return AudiencePortraitResponse(
        portrait=AudiencePortraitFields.model_validate(portrait),
        confidence=conf,
        data_coverage_score=dc,
        synthesis_blocked=bool(meta.get("synthesis_blocked", False)),
        data_quality_message=meta.get("data_quality_message"),
        data_quality_warnings=[str(x) for x in (meta.get("data_quality_warnings") or []) if str(x).strip()],
        portrait_grounding=dict(meta.get("portrait_grounding") or {}),
        interview_count=ic,
        segment_distribution=seg,
        evidence_count=int(ex["evidence_count"]),
        segment_coverage=dict(ex["segment_coverage"]),
        sample_quotes=[SampleQuoteItem.model_validate(x) for x in ex["sample_quotes"]],
        meta=meta_out,
    )


def _models_from_dicts[T](
    model_cls: type[T],
    rows: list[dict[str, Any]],
    *,
    limit: int = 24,
) -> list[T]:
    out: list[T] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        try:
            out.append(model_cls.model_validate(row))
        except Exception:
            continue
    return out


def _strategy_response(
    strategy: dict[str, Any],
    meta: dict[str, Any],
    ctx: dict[str, Any],
    *,
    cache_hit: bool,
) -> PRStrategyResponse:
    conf, ic, seg = confidence_from_context(ctx)
    meta_out = {**meta, "cache_hit": cache_hit}
    dc = float(meta.get("data_coverage_score", conf))
    pa_dicts = parse_priority_actions(strategy.get("priority_actions"))
    mm_dicts = build_impact_effort_matrix(pa_dicts)
    al_dicts = parse_alerts(strategy.get("alerts"))
    ex = explainability_bundle(ctx)
    dqm: str | None = meta.get("data_quality_message")
    if dqm is None and bool(meta.get("synthesis_blocked")):
        dqm = insufficient_synthesis_message(str(meta.get("output_language") or "ru"))
    if isinstance(dqm, str) and not dqm.strip():
        dqm = None

    raw_pg = strategy.get("pr_grounding")
    pr_grounding_list: list[dict[str, Any]] = [x for x in (raw_pg or []) if isinstance(x, dict)]
    pr_grounding = _models_from_dicts(PRGroundingRow, pr_grounding_list, limit=80)

    raw_ac = strategy.get("action_cards")
    ac_list: list[dict[str, Any]] = [x for x in (raw_ac or []) if isinstance(x, dict)]
    action_cards = _models_from_dicts(PRActionCardItem, ac_list, limit=40)

    dash_snap = meta.get("dashboard_snapshot") if isinstance(meta.get("dashboard_snapshot"), dict) else None
    if not dash_snap:
        dash_snap = dashboard_first_bundle(ctx)

    insufficient_data_obj: InsufficientDataPayload | None = None
    insuf_raw = meta.get("insufficient_data")
    if isinstance(insuf_raw, dict) and str(insuf_raw.get("status") or "") == "insufficient_data":
        try:
            insufficient_data_obj = InsufficientDataPayload.model_validate(insuf_raw)
        except Exception:
            insufficient_data_obj = None

    raw_ei = strategy.get("evidence_insights")
    ei_list: list[dict[str, Any]]
    if isinstance(raw_ei, list) and raw_ei:
        ei_list = [x for x in raw_ei if isinstance(x, dict)]
    else:
        ei_list = evidence_insights_from_grounding(
            pr_grounding_list,
            interview_count=max(1, int(ctx.get("interview_count") or ic or 1)),
        )
    evidence_insights_models = _models_from_dicts(EvidenceDrivenInsight, ei_list, limit=80)
    ei_n = len(evidence_insights_models)
    conf_adj = round(min(1.0, conf + 0.025 * min(ei_n, 20)), 2)
    dc_pct = int(round(min(100.0, max(0.0, dc * 100.0 if dc <= 1.0001 else dc))))

    base = PRStrategyResponse(
        dashboard_snapshot=dash_snap,
        evidence_insights=evidence_insights_models,
        insufficient_data=insufficient_data_obj,
        data_coverage_pct=dc_pct,
        brand_perception_summary=strategy.get("brand_perception_summary") or "",
        key_pr_insights=list(strategy.get("key_pr_insights") or []),
        reputational_risks=list(strategy.get("reputational_risks") or []),
        communication_gaps=list(strategy.get("communication_gaps") or []),
        recommended_messages=list(strategy.get("recommended_messages") or []),
        talking_points=list(strategy.get("talking_points") or []),
        media_hooks=list(strategy.get("media_hooks") or []),
        next_steps=list(strategy.get("next_steps") or []),
        confidence=conf_adj,
        data_coverage_score=dc,
        synthesis_blocked=bool(meta.get("synthesis_blocked", False)),
        data_quality_message=dqm,
        data_quality_warnings=[str(x) for x in (meta.get("data_quality_warnings") or []) if str(x).strip()],
        interview_count=ic,
        segment_distribution=seg,
        meta=meta_out,
        priority_actions=_models_from_dicts(PriorityActionItem, pa_dicts),
        impact_effort_matrix=_models_from_dicts(ImpactEffortMatrixItem, mm_dicts),
        alerts=_models_from_dicts(DecisionAlertItem, al_dicts),
        evidence_count=int(ex["evidence_count"]),
        segment_coverage=dict(ex["segment_coverage"]),
        sample_quotes=[SampleQuoteItem.model_validate(x) for x in ex["sample_quotes"]],
        pr_grounding=pr_grounding,
        action_cards=action_cards,
        pr_risk_alerts_v2=[],
    )
    v2 = _models_from_dicts(PRRiskAlertItem, build_pr_risk_alerts_v2(base, ctx), limit=20)
    return base.model_copy(update={"pr_risk_alerts_v2": v2})


async def invalidate_batch_llm_cache(session: AsyncSession, batch_id: UUID) -> None:
    repo = BatchLlmCacheRepository(session)
    await repo.delete_for_batch(batch_id)
    await session.commit()


async def get_or_create_audience_portrait_response(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    recalculate: bool,
    settings: Settings | None = None,
) -> AudiencePortraitResponse:
    st = settings or get_settings()
    repo = BatchLlmCacheRepository(session)
    key = make_cache_key(
        CACHE_KIND_PORTRAIT,
        batch.id,
        group_by,
        segment_value,
        output_language,
        multi_interview_mode=getattr(batch, "single_file_multi_interview_mode", True),
    )
    if not recalculate:
        row = await repo.get_by_cache_key(key)
        if row is not None:
            try:
                return AudiencePortraitResponse.model_validate(row.payload_json)
            except Exception:
                logger.warning("stale portrait cache key=%s — regenerating", key)

    portrait, meta, ctx = await generate_audience_portrait(
        session,
        batch,
        group_by=group_by,
        segment_value=segment_value,
        output_language=output_language,
        settings=st,
    )
    resp = _portrait_response(portrait, meta, ctx, cache_hit=False)
    await repo.upsert_payload(
        batch_id=batch.id,
        cache_kind=CACHE_KIND_PORTRAIT,
        cache_key=key,
        payload_json=resp.model_dump(mode="json"),
    )
    await session.commit()
    return resp


async def get_or_create_pr_strategy_response(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    recalculate: bool,
    settings: Settings | None = None,
    prefetched_context: dict[str, Any] | None = None,
    prefetched_portrait: dict[str, str] | None = None,
) -> PRStrategyResponse:
    st = settings or get_settings()
    repo = BatchLlmCacheRepository(session)
    key = make_cache_key(
        CACHE_KIND_STRATEGY,
        batch.id,
        group_by,
        segment_value,
        output_language,
        multi_interview_mode=getattr(batch, "single_file_multi_interview_mode", True),
    )
    if not recalculate:
        row = await repo.get_by_cache_key(key)
        if row is not None:
            try:
                return PRStrategyResponse.model_validate(row.payload_json)
            except Exception:
                logger.warning("stale pr_strategy cache key=%s — regenerating", key)

    strategy, meta, ctx = await generate_pr_strategy(
        session,
        batch,
        group_by=group_by,
        segment_value=segment_value,
        output_language=output_language,
        settings=st,
        prefetched_context=prefetched_context,
        prefetched_portrait=prefetched_portrait,
    )
    resp = _strategy_response(strategy, meta, ctx, cache_hit=False)
    await repo.upsert_payload(
        batch_id=batch.id,
        cache_kind=CACHE_KIND_STRATEGY,
        cache_key=key,
        payload_json=resp.model_dump(mode="json"),
    )
    await session.commit()
    return resp


async def build_full_report_response(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    output_language: str,
    recalculate: bool,
    settings: Settings | None = None,
) -> FullReportResponse:
    st = settings or get_settings()
    ctx = await build_portrait_context(session, batch, group_by=None, segment_value=None)
    from app.services.research_batch_dashboard_service import build_batch_dashboard

    dash_ctx = await build_batch_dashboard(session, batch, group_by=None)
    ev_dash = dash_ctx.get("evidence_dashboard") or {}
    tl_real = ev_dash.get("timeline_series_real") or ev_dash.get("timeline") or {}
    ctx["timeline_series_real"] = tl_real if isinstance(tl_real, dict) else {}

    portrait_resp = await get_or_create_audience_portrait_response(
        session,
        batch,
        group_by=None,
        segment_value=None,
        output_language=output_language,
        recalculate=recalculate,
        settings=st,
    )
    strategy_resp = await get_or_create_pr_strategy_response(
        session,
        batch,
        group_by=None,
        segment_value=None,
        output_language=output_language,
        recalculate=recalculate,
        settings=st,
        prefetched_context=ctx,
        prefetched_portrait=portrait_resp.portrait.model_dump(),
    )

    rep_repo = ResearchReportRepository(session)
    rep = await rep_repo.get_latest_for_batch(batch.id)
    executive = ""
    if rep is not None and rep.status == ReportStatus.READY and (rep.executive_summary or "").strip():
        executive = rep.executive_summary.strip()
    else:
        parts: list[str] = []
        if strategy_resp.brand_perception_summary:
            parts.append(strategy_resp.brand_perception_summary.strip())
        if portrait_resp.portrait.brand_perception:
            parts.append(portrait_resp.portrait.brand_perception.strip())
        if strategy_resp.key_pr_insights:
            parts.append(strategy_resp.key_pr_insights[0])
        executive = "\n\n".join(p for p in parts if p)[:4000]

    risks: list[str] = []
    for r in ctx.get("risks_bar") or []:
        lab = str((r or {}).get("label") or "").strip()
        if lab:
            risks.append(lab)
    risks.extend([x for x in strategy_resp.reputational_risks if x.strip()])
    risks = risks[:40]

    recommendations: list[str] = []
    recommendations.extend([x for x in strategy_resp.key_pr_insights if x.strip()][:12])
    recommendations.extend([x for x in strategy_resp.recommended_messages if x.strip()][:12])
    recommendations = recommendations[:36]

    next_steps = [x for x in strategy_resp.next_steps if x.strip()][:24]

    conf = round((portrait_resp.confidence + strategy_resp.confidence) / 2.0, 2)
    ic = int(ctx.get("interview_count") or 0)
    _, _, seg = confidence_from_context(ctx)

    meta = {
        "batch_id": str(batch.id),
        "has_ready_batch_report": bool(rep and rep.status == ReportStatus.READY),
        "report_id": str(rep.id) if rep else None,
    }
    ex = explainability_bundle(ctx)
    cust = build_custdev_bundle(ctx, portrait=portrait_resp, strategy=strategy_resp)
    risk_v2 = _models_from_dicts(PRRiskAlertItem, [x for x in (cust.get("pr_risk_alerts_v2") or []) if isinstance(x, dict)])
    return FullReportResponse(
        executive_summary=executive,
        audience_portrait=portrait_resp,
        pr_strategy=strategy_resp,
        risks=risks,
        recommendations=recommendations,
        next_steps=next_steps,
        confidence=conf,
        interview_count=ic,
        segment_distribution=seg,
        evidence_count=int(ex["evidence_count"]),
        segment_coverage=dict(ex["segment_coverage"]),
        sample_quotes=[SampleQuoteItem.model_validate(x) for x in ex["sample_quotes"]],
        meta=meta,
        priority_actions=strategy_resp.priority_actions,
        impact_effort_matrix=strategy_resp.impact_effort_matrix,
        alerts=strategy_resp.alerts,
        insight_graph=cust["insight_graph"],
        hierarchical_summary=cust["hierarchical_summary"],
        pr_risk_alerts=cust["pr_risk_alerts"],
        pr_risk_alerts_v2=risk_v2,
        message_lab=cust["message_lab"],
        narrative_builder=cust["narrative_builder"],
        trend_dashboard=cust["trend_dashboard"],
    )
