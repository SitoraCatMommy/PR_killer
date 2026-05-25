"""PR Strategy Generator: portrait + research evidence → actionable PR plan (LLM)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm_http import httpx_timeout_for_upstream_read
from app.infrastructure.settings import Settings, get_settings
from app.models.research_batch import ResearchBatch
from app.services.audience_portrait_service import build_portrait_context, run_portrait_generation_sync
from app.services.data_readiness_service import (
    assess_strict_pr_readiness,
    assess_synthesis_readiness,
    insufficient_synthesis_message,
)
from app.services.decision_layer_service import enrich_strategy_decision_layer
from app.services.evidence_driven_bundle import (
    attach_based_on_to_actions,
    dashboard_empty_for_llm,
    dashboard_first_bundle,
    evidence_insights_from_grounding,
    insufficient_data_payload,
    insufficient_missing_from_readiness,
    pr_quality_warning,
)
from app.services.pr_grounding_service import build_pr_grounding, enrich_action_cards_with_evidence

logger = logging.getLogger(__name__)


def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    if "\n" in s:
        lines = []
        for ln in s.splitlines():
            t = ln.strip().lstrip("-•* ").strip()
            if t:
                lines.append(t)
        return lines if lines else [s]
    return [s]


def _system_prompt(output_language: str) -> str:
    if output_language == "uz":
        return (
            "Siz PR-strateg bo'lisiz. Faqat berilgan audience_portrait va research_evidence asosida "
            "aniq, bajariladigan PR choralari va xabarlar yozing. Umumiy PR cliché va bo'sh va'dalardan qoching. "
            "Barcha chiqish oʻzbek tilida. Faqat bitta JSON obyekt (user xabardagi kalitlar)."
        )
    if output_language == "en":
        return (
            "You are a senior PR strategist. Produce an actionable PR plan grounded strictly in the provided "
            "audience_portrait and research_evidence (topics, risks, problems, patterns, insights, quotes). "
            "No generic PR fluff. Output language: English. Return a single JSON object with the keys specified "
            "in the user message."
        )
    return (
        "Ты senior PR-стратег. Сформируй готовую PR-стратегию строго на основе audience_portrait и "
        "research_evidence (темы, риски, проблемы, паттерны, инсайты, цитаты). Запрещены общие фразы без "
        "опоры на данные. Пиши как человек-аналитик: объясняй, что именно слышно в интервью и почему это "
        "важно для коммуникации; избегай канцелярита, голых списков label-ов и механических пересказов метрик. "
        "Каждый пункт должен быть применимым на практике. Язык: русский. "
        "Верни один JSON-объект с ключами из user-сообщения."
    )


def _user_payload(
    *,
    brand: str,
    output_language: str,
    segment_filter: dict[str, Any],
    audience_portrait: dict[str, str],
    research_evidence: dict[str, Any],
) -> str:
    body = {
        "task": "pr_strategy",
        "brand": brand,
        "output_language": output_language,
        "segment_filter": segment_filter,
        "audience_portrait": audience_portrait,
        "research_evidence": research_evidence,
        "required_output": {
            "action_cards": (
                "array of 6–14 objects ONLY — no long prose fields elsewhere. Each object EXACTLY: "
                "{action, for_segment, message, expected_effect, risk_if_ignored, evidence_refs}. "
                "channel: omit or empty string (server fills traceability). "
                "evidence_refs: array of 2–5 items; prefer objects {entity_id, text} copied from research_evidence.quotes "
                "when entity_id exists, else short verbatim strings from quotes/problems/risks only. "
                "If you cannot find 2 distinct fragments for a card, omit that card."
            ),
            "alerts": (
                "array of 3–8 objects {type, message, severity} — type one of risk | sentiment | trust; "
                "severity one of high | medium; message short, grounded in frequencies and at least one respondent quote "
                "when quote_backed_insights/quotes are present"
            ),
        },
        "rules": [
            "Output JSON MUST contain only action_cards and alerts (plus optional brand_perception_summary one sentence <= 280 chars).",
            "No paragraphs: action_cards are the sole strategy output.",
            "If segment_filter is set, bias for_segment toward that slice.",
            "Prefer research_evidence.quote_backed_insights over naked top_insights labels when explaining why an action matters.",
            "Do not invent statistics — tie message lines to evidence_refs snippets.",
        ],
    }
    return json.dumps(body, ensure_ascii=False)[:100_000]


def _static_strategy_blocked(msg: str) -> dict[str, Any]:
    return {
        "brand_perception_summary": msg,
        "key_pr_insights": [],
        "reputational_risks": [],
        "communication_gaps": [],
        "recommended_messages": [],
        "talking_points": [],
        "media_hooks": [],
        "next_steps": [],
        "priority_actions": [],
        "alerts": [],
        "pr_grounding": [],
        "action_cards": [],
    }


def _parse_strategy_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("strategy_not_object")
    out: dict[str, Any] = {}
    out["brand_perception_summary"] = str(data.get("brand_perception_summary") or "").strip()
    for k in (
        "key_pr_insights",
        "reputational_risks",
        "communication_gaps",
        "recommended_messages",
        "talking_points",
        "media_hooks",
        "next_steps",
    ):
        out[k] = _as_str_list(data.get(k))
    out["priority_actions"] = data.get("priority_actions")
    out["alerts"] = data.get("alerts")
    ac = data.get("action_cards")
    cards: list[dict[str, Any]] = []
    if isinstance(ac, list):
        for it in ac:
            if not isinstance(it, dict):
                continue
            bo = it.get("based_on") if isinstance(it.get("based_on"), list) else []
            based_on_llm = [str(x).strip() for x in bo if str(x).strip()][:24]
            cards.append(
                {
                    "action": str(it.get("action") or "").strip(),
                    "for_segment": str(it.get("for_segment") or "all").strip(),
                    "channel": str(it.get("channel") or "").strip(),
                    "message": str(it.get("message") or "").strip(),
                    "expected_effect": str(it.get("expected_effect") or "").strip(),
                    "risk_if_ignored": str(it.get("risk_if_ignored") or "").strip(),
                    "evidence_refs": it.get("evidence_refs") if isinstance(it.get("evidence_refs"), list) else [],
                    "based_on": based_on_llm,
                }
            )
    out["action_cards"] = [c for c in cards if c.get("action") or c.get("message")]
    return out


def _generate_pr_strategy_sync(user_message: str, output_language: str, settings: Settings) -> dict[str, Any]:
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError("openai_api_key_missing")
    read_s = max(180.0, float(settings.openai_http_timeout_seconds))
    client = OpenAI(api_key=key, timeout=httpx_timeout_for_upstream_read(read_seconds=read_s))
    completion = client.chat.completions.create(
        model=settings.openai_report_model,
        messages=[
            {"role": "system", "content": _system_prompt(output_language)},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.32,
    )
    raw = completion.choices[0].message.content if completion.choices else None
    if not raw:
        raise ValueError("empty_llm_response")
    return _parse_strategy_json(raw)


async def generate_pr_strategy(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    settings: Settings | None = None,
    prefetched_context: dict[str, Any] | None = None,
    prefetched_portrait: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    st = settings or get_settings()
    brand = (st.research_report_brand_name or "Click").strip() or "Click"

    ctx = prefetched_context or await build_portrait_context(
        session, batch, group_by=group_by, segment_value=segment_value
    )
    ctx["__output_language"] = output_language
    dash_snap = dashboard_first_bundle(ctx)
    empty_llm, missing_dash = dashboard_empty_for_llm(ctx)
    if empty_llm:
        ins = insufficient_data_payload(output_language, missing_dash)
        strategy = _static_strategy_blocked(ins["message"])
        readiness0 = assess_synthesis_readiness(ctx, output_language=output_language)
        meta = {
            "interview_count": ctx.get("interview_count"),
            "group_by": group_by,
            "segment_value": segment_value,
            "brand": brand,
            "llm_model": st.openai_report_model,
            "used_portrait": False,
            "synthesis_blocked": True,
            "data_coverage_score": readiness0.data_coverage_score,
            "data_quality_warnings": list(dict.fromkeys([*(readiness0.warnings or []), ins["message"]])),
            "data_quality_message": ins["message"],
            "output_language": output_language,
            "strict_pr_ready": False,
            "gates_checklist": [],
            "dashboard_snapshot": dash_snap,
            "insufficient_data": ins,
        }
        return strategy, meta, ctx

    strict = assess_strict_pr_readiness(ctx, output_language=output_language)
    readiness = assess_synthesis_readiness(ctx, output_language=output_language)
    if not readiness.can_synthesize or not strict.ready:
        msg = (
            strict.user_message
            if not strict.ready
            else insufficient_synthesis_message(output_language)
        )
        strategy = _static_strategy_blocked(msg)
        miss = insufficient_missing_from_readiness(
            strict_ready=strict.ready,
            strict_checklist=list(strict.checklist),
            can_synthesize=readiness.can_synthesize,
        )
        ins = insufficient_data_payload(output_language, miss or ["unknown"])
        meta = {
            "interview_count": ctx.get("interview_count"),
            "group_by": group_by,
            "segment_value": segment_value,
            "brand": brand,
            "llm_model": st.openai_report_model,
            "used_portrait": False,
            "synthesis_blocked": True,
            "data_coverage_score": readiness.data_coverage_score,
            "data_quality_warnings": list(
                dict.fromkeys([*(readiness.warnings or []), *( [strict.user_message] if strict.user_message else [])]),
            ),
            "data_quality_message": msg,
            "output_language": output_language,
            "strict_pr_ready": strict.ready,
            "gates_checklist": [
                {
                    "id": x.id,
                    "label": x.label,
                    "passed": x.passed,
                    "current": x.current,
                    "threshold": x.threshold,
                    "unit": x.unit,
                }
                for x in strict.checklist
            ],
            "dashboard_snapshot": dash_snap,
            "insufficient_data": ins,
        }
        return strategy, meta, ctx

    try:
        if prefetched_portrait is not None:
            portrait = dict(prefetched_portrait)
        else:
            portrait = await asyncio.to_thread(
                run_portrait_generation_sync,
                ctx,
                batch_name=batch.name or "",
                output_language=output_language,
                settings=st,
            )
    except Exception:
        logger.exception("pr_strategy: portrait step failed batch_id=%s", batch.id)
        raise

    segment_filter = {"group_by": group_by, "segment_value": segment_value}
    research_evidence = {
        "interview_count": ctx.get("interview_count"),
        "audience_snapshot": ctx.get("audience_snapshot"),
        "topics_pie": ctx.get("topics_pie"),
        "problems_bar": ctx.get("problems_bar"),
        "risks_bar": ctx.get("risks_bar"),
        "top_patterns": ctx.get("top_patterns"),
        "top_insights": ctx.get("top_insights"),
        "interview_evidence_summaries": (ctx.get("interview_evidence_summaries") or [])[:24],
        "quote_backed_insights": [
            x
            for x in (ctx.get("pr_insight_rollups") or [])[:18]
            if isinstance(x, dict) and (x.get("quotes") or [])
        ],
        "word_frequency": ctx.get("word_frequency"),
        "sentiment": ctx.get("sentiment"),
        "quotes": (ctx.get("quotes") or [])[:32],
    }

    user_msg = _user_payload(
        brand=brand,
        output_language=output_language,
        segment_filter=segment_filter,
        audience_portrait=portrait,
        research_evidence=research_evidence,
    )
    try:
        strategy = await asyncio.to_thread(_generate_pr_strategy_sync, user_msg, output_language, st)
    except Exception:
        logger.exception("pr_strategy: strategy step failed batch_id=%s", batch.id)
        raise

    enrich_strategy_decision_layer(strategy, ctx, output_language=output_language)
    quotes_list = list(ctx.get("quotes") or [])
    try:
        raw_cards = strategy.get("action_cards") or []
        if isinstance(raw_cards, list) and raw_cards:
            strategy["action_cards"] = enrich_action_cards_with_evidence(
                [x for x in raw_cards if isinstance(x, dict)],
                quotes_list,
            )
    except Exception:
        logger.exception("action_cards enrichment failed batch_id=%s", batch.id)
        strategy["action_cards"] = strategy.get("action_cards") or []
    try:
        strategy["pr_grounding"] = build_pr_grounding(
            strategy,
            quotes_list,
        )
    except Exception:
        logger.exception("pr_grounding failed batch_id=%s", batch.id)
        strategy["pr_grounding"] = []

    evid_raw = evidence_insights_from_grounding(
        [x for x in (strategy.get("pr_grounding") or []) if isinstance(x, dict)],
        interview_count=int(ctx.get("interview_count") or 1),
    )
    strategy["evidence_insights"] = evid_raw
    try:
        strategy["action_cards"] = attach_based_on_to_actions(
            [x for x in (strategy.get("action_cards") or []) if isinstance(x, dict)],
            evid_raw,
        )
        strategy["priority_actions"] = [
            {
                "action": str(c.get("action") or c.get("message") or "").strip()[:500],
                "impact": "high" if str(c.get("evidence_status")) == "ok" else "medium",
                "effort": "medium",
                "reason": str(c.get("message") or "")[:800],
                "based_on": [str(x).strip() for x in (c.get("based_on") or []) if str(x).strip()][:24],
            }
            for c in (strategy.get("action_cards") or [])
            if isinstance(c, dict) and str(c.get("evidence_status") or "") == "ok"
        ][:16]
        strategy["impact_effort_matrix"] = [
            {"action": a["action"], "impact": a["impact"], "effort": a["effort"]}
            for a in (strategy.get("priority_actions") or [])
        ]
    except Exception:
        logger.exception("evidence_insights / based_on attach failed batch_id=%s", batch.id)

    r2 = assess_synthesis_readiness(ctx, output_language=output_language)
    strict_ok = assess_strict_pr_readiness(ctx, output_language=output_language)
    pqw = pr_quality_warning(ctx)
    wlist = list(r2.warnings or [])
    if pqw:
        wlist = list(dict.fromkeys([*wlist, pqw]))
    meta = {
        "interview_count": ctx.get("interview_count"),
        "group_by": group_by,
        "segment_value": segment_value,
        "brand": brand,
        "llm_model": st.openai_report_model,
        "used_portrait": True,
        "synthesis_blocked": False,
        "data_coverage_score": r2.data_coverage_score,
        "data_quality_warnings": wlist,
        "data_quality_message": None,
        "output_language": output_language,
        "strict_pr_ready": strict_ok.ready,
        "gates_checklist": [
            {
                "id": x.id,
                "label": x.label,
                "passed": x.passed,
                "current": x.current,
                "threshold": x.threshold,
                "unit": x.unit,
            }
            for x in strict_ok.checklist
        ],
        "dashboard_snapshot": dash_snap,
        "insufficient_data": None,
    }
    return strategy, meta, ctx
