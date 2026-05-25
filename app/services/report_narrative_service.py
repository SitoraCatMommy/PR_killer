"""Turn structured batch report models into readable sections (public API + exports)."""

from __future__ import annotations

from app.schemas.research_batch import FullReportResponse, PublicReportSection


def _titles(lang: str) -> dict[str, str]:
    lg = (lang or "ru").strip().lower()[:8]
    if lg == "en":
        return {
            "exec": "Executive summary",
            "portrait": "Audience portrait",
            "strategy": "PR & communications",
            "risks": "Risks",
            "recs": "Recommendations",
            "next": "Next steps",
        }
    if lg == "uz":
        return {
            "exec": "Ijrochi xulosa",
            "portrait": "Auditoriya portreti",
            "strategy": "PR va kommunikatsiya",
            "risks": "Xavflar",
            "recs": "Tavsiyalar",
            "next": "Keyingi qadamlar",
        }
    return {
        "exec": "Резюме",
        "portrait": "Портрет аудитории",
        "strategy": "PR и коммуникации",
        "risks": "Риски",
        "recs": "Рекомендации",
        "next": "Следующие шаги",
    }


def narrative_sections_from_full_report(full: FullReportResponse, *, lang: str = "ru") -> list[PublicReportSection]:
    t = _titles(lang)
    sections: list[PublicReportSection] = []
    if (full.executive_summary or "").strip():
        sections.append(PublicReportSection(title=t["exec"], body=full.executive_summary.strip()))

    p = full.audience_portrait.portrait
    portrait_body = "\n\n".join(
        part
        for part in (
            p.decision_making,
            p.fears,
            p.trust_drivers,
            p.pain_points,
            p.language_style,
            p.brand_perception,
            p.emotional_triggers,
        )
        if (part or "").strip()
    )
    if portrait_body.strip():
        sections.append(PublicReportSection(title=t["portrait"], body=portrait_body.strip()))

    s = full.pr_strategy
    strat_parts: list[str] = []
    if (s.brand_perception_summary or "").strip():
        strat_parts.append(s.brand_perception_summary.strip())
    for items in (
        s.key_pr_insights,
        s.reputational_risks,
        s.communication_gaps,
        s.recommended_messages,
        s.talking_points,
        s.media_hooks,
    ):
        if items:
            strat_parts.append("\n".join(f"• {x}" for x in items if str(x).strip()))
    strat_body = "\n\n".join(strat_parts)
    if strat_body.strip():
        sections.append(PublicReportSection(title=t["strategy"], body=strat_body.strip()))

    if full.risks:
        sections.append(
            PublicReportSection(title=t["risks"], body="\n".join(f"• {r}" for r in full.risks if r.strip()))
        )
    if full.recommendations:
        sections.append(
            PublicReportSection(
                title=t["recs"], body="\n".join(f"• {r}" for r in full.recommendations if r.strip())
            )
        )
    if full.next_steps:
        sections.append(
            PublicReportSection(title=t["next"], body="\n".join(f"• {r}" for r in full.next_steps if r.strip()))
        )
    return sections


def markdown_from_sections(batch_name: str, sections: list[PublicReportSection]) -> str:
    parts = [f"# {batch_name.strip() or 'Report'}\n"]
    for sec in sections:
        parts.append(f"\n## {sec.title}\n\n{sec.body}\n")
    return "".join(parts).strip()
