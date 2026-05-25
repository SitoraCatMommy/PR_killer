from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.research_languages import normalize_output_language
from app.infrastructure.settings import Settings, get_settings
from app.models.research_batch import ResearchBatch
from app.models.project import Project
from app.schemas.research_batch import FullReportResponse, PublicReportResponse
from app.services.batch_cached_llm_service import build_full_report_response
from app.services.report_narrative_service import markdown_from_sections, narrative_sections_from_full_report
from app.services.research_batch_dashboard_service import build_batch_dashboard


async def build_public_report_for_batch(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    full: FullReportResponse | None = None,
    recalculate: bool = False,
    settings: Settings | None = None,
) -> PublicReportResponse:
    st = settings or get_settings()
    proj = await session.get(Project, batch.project_id)
    b_lang = getattr(batch, "output_language", None)
    if b_lang and str(b_lang).strip():
        lang = normalize_output_language(str(b_lang), default="ru")
    else:
        lang = normalize_output_language(proj.output_language if proj else None, default="ru")

    report = full
    if report is None:
        report = await build_full_report_response(
            session,
            batch,
            output_language=lang,
            recalculate=recalculate,
            settings=st,
        )

    sections = narrative_sections_from_full_report(report, lang=lang)
    md = markdown_from_sections(batch.name, sections)
    dash = await build_batch_dashboard(session, batch, group_by=None)
    ed = dash.get("evidence_dashboard") or {}
    appendix = {
        "traceability_rows": (ed.get("traceability") or {}).get("rows", [])[:50],
        "pr_insight_rollups": ed.get("pr_insight_rollups", [])[:50],
    }
    kpis = ed.get("kpis") or {}
    tpr = ed.get("topics_problems_risks") or {}
    topics_top = list(tpr.get("topics_pie") or dash.get("topics_pie") or [])[:8]
    risks_top = list(tpr.get("risks_bar") or dash.get("risks_bar") or [])[:8]
    snapshot = {
        "kpis": kpis,
        "top_topics": topics_top,
        "top_risks": risks_top,
        "sentiment": ed.get("sentiment") or dash.get("sentiment") or {},
        "counts": {
            "interviews": int(kpis.get("interview_count") or 0),
            "evidence_quotes": int(kpis.get("evidence_quotes") or 0),
            "entity_rows": int(kpis.get("entity_rows") or 0),
            "processed_interviews_estimate": int(kpis.get("processed_interviews_estimate") or 0),
        },
        "pr_taxonomy_totals": ed.get("pr_taxonomy_totals") or dash.get("pr_taxonomy_totals") or [],
        "timeline": ed.get("timeline") or {},
        "appendix_link": {
            "traceability_rows_in_response": len(appendix["traceability_rows"]),
            "pr_insight_rollups_in_response": len(appendix["pr_insight_rollups"]),
            "evidence_appendix_keys": ["traceability_rows", "pr_insight_rollups"],
        },
    }
    return PublicReportResponse(
        batch_id=batch.id,
        batch_name=batch.name,
        executive_summary=report.executive_summary,
        sections=sections,
        risks=report.risks,
        recommendations=report.recommendations,
        next_steps=report.next_steps,
        evidence_count=report.evidence_count,
        segment_coverage=report.segment_coverage,
        sample_quotes=report.sample_quotes,
        narrative_markdown=md,
        meta={
            "batch_id": str(batch.id),
            "project_id": str(batch.project_id),
            "language": lang,
        },
        dashboard_snapshot=snapshot,
        evidence_appendix=appendix,
    )
