"""DB-backed cache + orchestration for project-level LLM endpoints."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ReportStatus
from app.infrastructure.settings import Settings, get_settings
from app.repositories.project_llm_cache_repository import ProjectLlmCacheRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.schemas.research_batch import (
    AudiencePortraitResponse,
    FullReportResponse,
    PRStrategyResponse,
)
from app.services.audience_portrait_service import generate_audience_portrait
from app.services.batch_cached_llm_service import (
    CACHE_KIND_PORTRAIT,
    CACHE_KIND_STRATEGY,
    _portrait_response,
    _strategy_response,
    confidence_from_context,
    make_cache_key,
)
from app.services.batch_data_fingerprint import compute_project_corpora_fingerprint
from app.services.custdev_report_bundle import build_custdev_bundle, build_pr_risk_alerts_v2
from app.services.explainability_service import explainability_bundle
from app.services.pr_strategy_service import generate_pr_strategy
from app.services.corpus_view import load_corpus_view
from app.services.research_batch_dashboard_service import build_project_dashboard

logger = logging.getLogger(__name__)


def make_project_cache_key(
    kind: str,
    project_id: UUID,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    *,
    multi_interview_mode: bool | None = None,
    data_revision: str | None = None,
) -> str:
    return make_cache_key(
        kind,
        project_id,
        group_by,
        segment_value,
        output_language,
        multi_interview_mode=multi_interview_mode,
        data_revision=data_revision,
    ).replace(f"{kind}:{project_id}", f"{kind}:project:{project_id}", 1)


async def invalidate_project_llm_cache(session: AsyncSession, project_id: UUID) -> None:
    repo = ProjectLlmCacheRepository(session)
    await repo.delete_for_project(project_id)
    await session.commit()


async def get_or_create_project_audience_portrait_response(
    session: AsyncSession,
    project_id: UUID,
    *,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    recalculate: bool,
    settings: Settings | None = None,
) -> AudiencePortraitResponse:
    st = settings or get_settings()
    batch_view = await load_corpus_view(session, project_id)
    repo = ProjectLlmCacheRepository(session)
    fp = await compute_project_corpora_fingerprint(session, project_id)
    key = make_project_cache_key(
        CACHE_KIND_PORTRAIT,
        project_id,
        group_by,
        segment_value,
        output_language,
        multi_interview_mode=getattr(batch_view, "single_file_multi_interview_mode", True),
        data_revision=fp,
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
        batch_view,  # type: ignore[arg-type]
        group_by=group_by,
        segment_value=segment_value,
        output_language=output_language,
        settings=st,
    )
    resp = _portrait_response(portrait, meta, ctx, cache_hit=False)
    await repo.upsert_payload(
        project_id=project_id,
        cache_kind=CACHE_KIND_PORTRAIT,
        cache_key=key,
        payload_json=resp.model_dump(mode="json"),
    )
    await session.commit()
    return resp


async def get_or_create_project_pr_strategy_response(
    session: AsyncSession,
    project_id: UUID,
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
    batch_view = await load_corpus_view(session, project_id)
    repo = ProjectLlmCacheRepository(session)
    fp = await compute_project_corpora_fingerprint(session, project_id)
    key = make_project_cache_key(
        CACHE_KIND_STRATEGY,
        project_id,
        group_by,
        segment_value,
        output_language,
        multi_interview_mode=getattr(batch_view, "single_file_multi_interview_mode", True),
        data_revision=fp,
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
        batch_view,  # type: ignore[arg-type]
        group_by=group_by,
        segment_value=segment_value,
        output_language=output_language,
        settings=st,
        prefetched_context=prefetched_context,
        prefetched_portrait=prefetched_portrait,
    )
    resp = _strategy_response(strategy, meta, ctx, cache_hit=False)
    await repo.upsert_payload(
        project_id=project_id,
        cache_kind=CACHE_KIND_STRATEGY,
        cache_key=key,
        payload_json=resp.model_dump(mode="json"),
    )
    await session.commit()
    return resp


async def build_project_full_report_response(
    session: AsyncSession,
    project_id: UUID,
    *,
    output_language: str,
    recalculate: bool,
    settings: Settings | None = None,
) -> FullReportResponse:
    from app.schemas.research_batch import PRRiskAlertItem, SampleQuoteItem
    from app.services.batch_cached_llm_service import _models_from_dicts
    from app.services.audience_portrait_service import build_portrait_context

    st = settings or get_settings()
    batch_view = await load_corpus_view(session, project_id)
    ctx = await build_portrait_context(session, batch_view, group_by=None, segment_value=None)  # type: ignore[arg-type]
    dash_ctx = await build_project_dashboard(session, project_id, group_by=None)
    ev_dash = dash_ctx.get("evidence_dashboard") or {}
    tl_real = ev_dash.get("timeline_series_real") or ev_dash.get("timeline") or {}
    ctx["timeline_series_real"] = tl_real if isinstance(tl_real, dict) else {}

    portrait_resp = await get_or_create_project_audience_portrait_response(
        session,
        project_id,
        group_by=None,
        segment_value=None,
        output_language=output_language,
        recalculate=recalculate,
        settings=st,
    )
    strategy_resp = await get_or_create_project_pr_strategy_response(
        session,
        project_id,
        group_by=None,
        segment_value=None,
        output_language=output_language,
        recalculate=recalculate,
        settings=st,
        prefetched_context=ctx,
        prefetched_portrait=portrait_resp.portrait.model_dump(),
    )

    rep_repo = ResearchReportRepository(session)
    rep = await rep_repo.get_latest_for_project(project_id)
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
        "project_id": str(project_id),
        "has_ready_project_report": bool(rep and rep.status == ReportStatus.READY),
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
