"""Compare two audience segments within one research batch (metrics + cached LLM summaries)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.settings import Settings, get_settings
from app.models.research_batch import ResearchBatch
from app.schemas.research_batch import AudiencePortraitResponse, PRStrategyResponse
from app.services.audience_portrait_service import build_portrait_context
from app.services.batch_cached_llm_service import (
    get_or_create_audience_portrait_response,
    get_or_create_pr_strategy_response,
)
from app.services.decision_layer_service import (
    build_compare_decision_payload,
    fallback_compare_priority_actions,
    generate_compare_decision_layer_sync,
    heuristic_alerts_segment_compare,
    merge_alerts,
)
from app.repositories.interview_unit_repository import list_unit_id_strings_for_documents
from app.services.research_batch_dashboard_service import (
    DASHBOARD_GROUP_BY_FIELDS,
    _load_metadata_maps,
    _segment_label,
    build_batch_dashboard,
)

logger = logging.getLogger(__name__)


def resolve_interview_unit_segment(requested: str, labels: list[str]) -> str | None:
    req = (requested or "").strip().lower().replace("-", "")
    if not req:
        return None
    for lab in labels:
        ls = str(lab).strip().lower().replace("-", "")
        if ls == req or ls.startswith(req) or (len(req) >= 8 and req in ls):
            return str(lab)
    return None


def _ic_interview_unit(_seg: str) -> int:
    return 1


def _normalize_segment_token(raw: str) -> str:
    x = (raw or "").strip().lower()
    for ch in ("\u2013", "\u2014", "\u2212"):  # en dash, em dash, minus sign
        x = x.replace(ch, "-")
    return " ".join(x.split())


def _collect_segment_labels_for_group_by(
    batch: ResearchBatch,
    *,
    doc_meta: dict,
    audio_meta: dict,
    group_by: str,
) -> list[str]:
    keys: list[str] = []
    for s in batch.sources:
        if s.source_document_id:
            m = dict(doc_meta.get(s.source_document_id) or {})
        elif s.source_audio_id:
            m = dict(audio_meta.get(s.source_audio_id) or {})
        else:
            continue
        keys.append(_segment_label(m, group_by))
    return keys


def resolve_segment_value(
    requested: str,
    batch: ResearchBatch,
    *,
    doc_meta: dict,
    audio_meta: dict,
    group_by: str,
) -> str | None:
    """Map user input (e.g. 18-24 vs 18–24) to canonical `_segment_label` value present in batch."""
    req = (requested or "").strip()
    if not req:
        return None
    req_n = _normalize_segment_token(req)
    candidates = _collect_segment_labels_for_group_by(
        batch, doc_meta=doc_meta, audio_meta=audio_meta, group_by=group_by
    )
    for c in candidates:
        if c == req:
            return c
    for c in candidates:
        if _normalize_segment_token(c) == req_n:
            return c
    return None


def _find_segment_block(dashboard: dict[str, Any], segment_key: str) -> dict[str, Any] | None:
    sk_n = _normalize_segment_token(segment_key)
    for row in dashboard.get("segment_breakdown") or []:
        k = str(row.get("segment_key") or "")
        if k == segment_key or _normalize_segment_token(k) == sk_n:
            return row
    return None


def _empty_side(segment_key: str) -> dict[str, Any]:
    return {
        "segment_key": segment_key,
        "interview_count": 0,
        "topic_frequency": [],
        "problem_frequency": [],
        "risk_frequency": [],
        "sentiment": {"positive_signals": 0, "negative_signals": 0, "balance": "unknown"},
        "top_insights": [],
        "word_frequency": [],
        "audience_portrait_summary": "",
        "pr_strategy_summary": "",
    }


def _merge_dashboard_block(segment_key: str, block: dict[str, Any] | None, ic: int) -> dict[str, Any]:
    if not block:
        return _empty_side(segment_key)
    return {
        "segment_key": segment_key,
        "interview_count": ic,
        "topic_frequency": list(block.get("topics_pie") or []),
        "problem_frequency": list(block.get("problems_bar") or []),
        "risk_frequency": list(block.get("risks_bar") or []),
        "sentiment": dict(block.get("sentiment") or {}),
        "top_insights": list(block.get("top_insights") or []),
        "word_frequency": list(block.get("word_frequency") or []),
        "audience_portrait_summary": "",
        "pr_strategy_summary": "",
    }


def _portrait_summary(p: AudiencePortraitResponse, *, max_chars: int = 1400) -> str:
    parts: list[str] = []
    pf = p.portrait
    for title, text in (
        ("brand_perception", pf.brand_perception),
        ("trust_drivers", pf.trust_drivers),
        ("pain_points", pf.pain_points),
        ("decision_making", pf.decision_making),
    ):
        t = (text or "").strip()
        if t:
            parts.append(t[:500])
    out = "\n\n".join(parts)
    return out[:max_chars]


def _strategy_summary(s: PRStrategyResponse, *, max_chars: int = 1200) -> str:
    parts: list[str] = []
    if (s.brand_perception_summary or "").strip():
        parts.append(s.brand_perception_summary.strip()[:600])
    for x in (s.key_pr_insights or [])[:3]:
        xs = str(x).strip()
        if xs:
            parts.append(xs[:280])
    out = "\n".join(parts)
    return out[:max_chars]


def _label_set(rows: list[Any], *, key: str = "label") -> set[str]:
    out: set[str] = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        lab = str(r.get(key) or "").strip()
        if lab:
            out.add(lab)
    return out


def _pattern_text_set(rows: list[Any]) -> set[str]:
    out: set[str] = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t = str(r.get("text") or "").strip()
        if t:
            out.add(t[:120])
    return out


def _build_differences_and_pr(
    *,
    side_a: dict[str, Any],
    side_b: dict[str, Any],
    portrait_a: AudiencePortraitResponse,
    portrait_b: AudiencePortraitResponse,
    strategy_a: PRStrategyResponse,
    strategy_b: PRStrategyResponse,
    lang: str,
) -> tuple[list[dict[str, str]], list[str]]:
    lg = (lang or "ru").strip().lower()[:8]

    topics_a = _label_set(side_a.get("topic_frequency") or [])
    topics_b = _label_set(side_b.get("topic_frequency") or [])
    prob_a = _label_set(side_a.get("problem_frequency") or [])
    prob_b = _label_set(side_b.get("problem_frequency") or [])
    risk_a = _label_set(side_a.get("risk_frequency") or [])
    risk_b = _label_set(side_b.get("risk_frequency") or [])
    pat_a = _pattern_text_set(side_a.get("top_patterns") or [])
    pat_b = _pattern_text_set(side_b.get("top_patterns") or [])

    sent_a = side_a.get("sentiment") or {}
    sent_b = side_b.get("sentiment") or {}
    bal_a = str(sent_a.get("balance") or "")
    bal_b = str(sent_b.get("balance") or "")

    differences: list[dict[str, str]] = []

    def _t(ru: str, uz: str, en: str) -> str:
        if lg == "uz":
            return uz
        if lg == "en":
            return en
        return ru

    common_t = topics_a & topics_b
    only_a_t = topics_a - topics_b
    only_b_t = topics_b - topics_a
    differences.append(
        {
            "dimension": "topics",
            "summary": _t(
                f"Общие темы ({len(common_t)}): {', '.join(sorted(common_t)[:6]) or '—'}. "
                f"Сильнее только в «{side_a['segment_key']}»: {', '.join(sorted(only_a_t)[:5]) or '—'}. "
                f"Только в «{side_b['segment_key']}»: {', '.join(sorted(only_b_t)[:5]) or '—'}.",
                f"Umumiy mavzular ({len(common_t)}): {', '.join(sorted(common_t)[:6]) or '—'}. "
                f"Faqat «{side_a['segment_key']}»: {', '.join(sorted(only_a_t)[:5]) or '—'}. "
                f"Faqat «{side_b['segment_key']}»: {', '.join(sorted(only_b_t)[:5]) or '—'}.",
                f"Shared topics ({len(common_t)}): {', '.join(sorted(common_t)[:6]) or '—'}. "
                f"Only in {side_a['segment_key']}: {', '.join(sorted(only_a_t)[:5]) or '—'}. "
                f"Only in {side_b['segment_key']}: {', '.join(sorted(only_b_t)[:5]) or '—'}.",
            ),
        }
    )

    common_p = prob_a & prob_b
    differences.append(
        {
            "dimension": "problems",
            "summary": _t(
                f"Пересечение проблем/потребностей: {len(common_p)} совпадений по формулировкам. "
                f"Уникальные у «{side_a['segment_key']}»: {len(prob_a - prob_b)}, "
                f"у «{side_b['segment_key']}»: {len(prob_b - prob_a)}.",
                f"Muammolar kesishmasi: {len(common_p)}. "
                f"«{side_a['segment_key']}» uchun noyob: {len(prob_a - prob_b)}, "
                f"«{side_b['segment_key']}» uchun: {len(prob_b - prob_a)}.",
                f"Problem label overlap: {len(common_p)}. "
                f"Unique to {side_a['segment_key']}: {len(prob_a - prob_b)}, "
                f"to {side_b['segment_key']}: {len(prob_b - prob_a)}.",
            ),
        }
    )

    only_a_r = risk_a - risk_b
    only_b_r = risk_b - risk_a
    differences.append(
        {
            "dimension": "risks",
            "summary": _t(
                f"Риски только в «{side_a['segment_key']}»: {', '.join(sorted(only_a_r)[:6]) or '—'}. "
                f"Только в «{side_b['segment_key']}»: {', '.join(sorted(only_b_r)[:6]) or '—'}.",
                f"Faqat «{side_a['segment_key']}» xavflari: {', '.join(sorted(only_a_r)[:6]) or '—'}. "
                f"Faqat «{side_b['segment_key']}»: {', '.join(sorted(only_b_r)[:6]) or '—'}.",
                f"Risks only in {side_a['segment_key']}: {', '.join(sorted(only_a_r)[:6]) or '—'}. "
                f"Only in {side_b['segment_key']}: {', '.join(sorted(only_b_r)[:6]) or '—'}.",
            ),
        }
    )

    differences.append(
        {
            "dimension": "sentiment",
            "summary": _t(
                f"Тональность: «{side_a['segment_key']}» — {bal_a or 'n/a'} "
                f"(+{sent_a.get('positive_signals', 0)}/−{sent_a.get('negative_signals', 0)}); "
                f"«{side_b['segment_key']}» — {bal_b or 'n/a'} "
                f"(+{sent_b.get('positive_signals', 0)}/−{sent_b.get('negative_signals', 0)}).",
                f"Sentiment: «{side_a['segment_key']}» — {bal_a or 'n/a'}; «{side_b['segment_key']}» — {bal_b or 'n/a'}.",
                f"Sentiment: {side_a['segment_key']} — {bal_a or 'n/a'} "
                f"(+{sent_a.get('positive_signals', 0)}/−{sent_a.get('negative_signals', 0)}); "
                f"{side_b['segment_key']} — {bal_b or 'n/a'} "
                f"(+{sent_b.get('positive_signals', 0)}/−{sent_b.get('negative_signals', 0)}).",
            ),
        }
    )

    common_pat = pat_a & pat_b
    stronger_a = pat_a - pat_b
    stronger_b = pat_b - pat_a
    differences.append(
        {
            "dimension": "patterns",
            "summary": _t(
                f"Общие паттерны: {len(common_pat)}. Ярче в «{side_a['segment_key']}»: "
                f"{', '.join(sorted(stronger_a)[:4]) or '—'}. В «{side_b['segment_key']}»: "
                f"{', '.join(sorted(stronger_b)[:4]) or '—'}.",
                f"Umumiy naqshlar: {len(common_pat)}. «{side_a['segment_key']}» da kuchliroq: "
                f"{', '.join(sorted(stronger_a)[:4]) or '—'}. «{side_b['segment_key']}»: "
                f"{', '.join(sorted(stronger_b)[:4]) or '—'}.",
                f"Shared patterns: {len(common_pat)}. More specific to {side_a['segment_key']}: "
                f"{', '.join(sorted(stronger_a)[:4]) or '—'}. To {side_b['segment_key']}: "
                f"{', '.join(sorted(stronger_b)[:4]) or '—'}.",
            ),
        }
    )

    trust_a = (portrait_a.portrait.trust_drivers or "").strip()[:320]
    trust_b = (portrait_b.portrait.trust_drivers or "").strip()[:320]
    differences.append(
        {
            "dimension": "trust",
            "summary": _t(
                f"Драйверы доверия: «{side_a['segment_key']}» — {trust_a or 'мало сигналов'}. "
                f"«{side_b['segment_key']}» — {trust_b or 'мало сигналов'}.",
                f"Ishonch: «{side_a['segment_key']}» — {trust_a or 'kam'}. «{side_b['segment_key']}» — {trust_b or 'kam'}.",
                f"Trust drivers: {side_a['segment_key']} — {trust_a or 'thin evidence'}. "
                f"{side_b['segment_key']} — {trust_b or 'thin evidence'}.",
            ),
        }
    )

    pain_a = (portrait_a.portrait.pain_points or "").strip()[:320]
    pain_b = (portrait_b.portrait.pain_points or "").strip()[:320]
    differences.append(
        {
            "dimension": "pain",
            "summary": _t(
                f"Болевые точки: «{side_a['segment_key']}» — {pain_a or '—'}; "
                f"«{side_b['segment_key']}» — {pain_b or '—'}.",
                f"Dard nuqtalari: «{side_a['segment_key']}» — {pain_a or '—'}; «{side_b['segment_key']}» — {pain_b or '—'}.",
                f"Pain points: {side_a['segment_key']} — {pain_a or '—'}; {side_b['segment_key']} — {pain_b or '—'}.",
            ),
        }
    )

    brand_a = (portrait_a.portrait.brand_perception or "").strip()[:360]
    brand_b = (portrait_b.portrait.brand_perception or "").strip()[:360]
    differences.append(
        {
            "dimension": "narrative",
            "summary": _t(
                f"Восприятие контекста/бренда: «{side_a['segment_key']}» — {brand_a or '—'}; "
                f"«{side_b['segment_key']}» — {brand_b or '—'}.",
                f"Kontekst: «{side_a['segment_key']}» — {brand_a or '—'}; «{side_b['segment_key']}» — {brand_b or '—'}.",
                f"Brand/context perception: {side_a['segment_key']} — {brand_a or '—'}; "
                f"{side_b['segment_key']} — {brand_b or '—'}.",
            ),
        }
    )

    pr_impl: list[str] = []
    gaps_a = [str(x).strip() for x in (strategy_a.communication_gaps or []) if str(x).strip()][:4]
    gaps_b = [str(x).strip() for x in (strategy_b.communication_gaps or []) if str(x).strip()][:4]
    if gaps_a or gaps_b:
        pr_impl.append(
            _t(
                f"Разные пробелы в коммуникации: «{side_a['segment_key']}» — {gaps_a[0] if gaps_a else '—'}; "
                f"«{side_b['segment_key']}» — {gaps_b[0] if gaps_b else '—'}.",
                f"Turli kommunikatsiya bo'shliqlari: «{side_a['segment_key']}» / «{side_b['segment_key']}».",
                f"Different comms gaps between {side_a['segment_key']} and {side_b['segment_key']}.",
            )
        )

    for r in sorted(only_a_r)[:3]:
        pr_impl.append(
            _t(
                f"Риск «{r}» усилен в сегменте «{side_a['segment_key']}» — проверьте сообщения и доказательства.",
                f"«{r}» xavfi «{side_a['segment_key']}» da — xabarlar va dalillar.",
                f"Risk “{r}” is more salient in {side_a['segment_key']}: adjust proof points and messaging.",
            )
        )
    for r in sorted(only_b_r)[:3]:
        pr_impl.append(
            _t(
                f"Риск «{r}» выражен в «{side_b['segment_key']}» — отдельная линия Q&A и медиаготовность.",
                f"«{r}» «{side_b['segment_key']}» uchun alohida Q&A.",
                f"Risk “{r}” is more salient in {side_b['segment_key']}: prepare Q&A and media lines.",
            )
        )

    msg_a = [str(x).strip() for x in (strategy_a.recommended_messages or []) if str(x).strip()][:2]
    msg_b = [str(x).strip() for x in (strategy_b.recommended_messages or []) if str(x).strip()][:2]
    if msg_a or msg_b:
        pr_impl.append(
            _t(
                f"Развести ключевые формулировки: для «{side_a['segment_key']}» — {msg_a[0] if msg_a else '—'}; "
                f"для «{side_b['segment_key']}» — {msg_b[0] if msg_b else '—'}.",
                f"Xabarlar: «{side_a['segment_key']}» / «{side_b['segment_key']}» uchun alohida formulalar.",
                f"Split core messages: lead with different proof for {side_a['segment_key']} vs {side_b['segment_key']}.",
            )
        )

    if not pr_impl:
        pr_impl.append(
            _t(
                "Сегменты близки по рискам и темам — используйте единый каркас сообщений с микронастройкой тона.",
                "Segmentlar yaqin — yagona ramka, mayda ton farqi.",
                "Segments align on risks/topics: one narrative frame with tone micro-adjustments.",
            )
        )

    return differences, pr_impl[:12]


async def compare_batch_segments(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str,
    segment_a: str,
    segment_b: str,
    output_language: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    st = settings or get_settings()
    gb = group_by.strip()
    if gb not in DASHBOARD_GROUP_BY_FIELDS:
        raise ValueError("invalid_group_by")

    doc_ids = [s.source_document_id for s in batch.sources if s.source_document_id]
    audio_ids = [s.source_audio_id for s in batch.sources if s.source_audio_id]
    doc_meta, audio_meta, _ = await _load_metadata_maps(session, doc_ids, audio_ids)

    if gb == "interview_unit":
        labels = await list_unit_id_strings_for_documents(session, doc_ids)
        ra = resolve_interview_unit_segment(segment_a, labels)
        rb = resolve_interview_unit_segment(segment_b, labels)
    else:
        ra = resolve_segment_value(segment_a, batch, doc_meta=doc_meta, audio_meta=audio_meta, group_by=gb)
        rb = resolve_segment_value(segment_b, batch, doc_meta=doc_meta, audio_meta=audio_meta, group_by=gb)
    if ra is None:
        raise ValueError("segment_a_unknown")
    if rb is None:
        raise ValueError("segment_b_unknown")
    if ra == rb:
        raise ValueError("segments_equal")

    dash = await build_batch_dashboard(session, batch, group_by=gb)
    block_a = _find_segment_block(dash, ra)
    block_b = _find_segment_block(dash, rb)

    def _ic_for(seg: str) -> int:
        n = 0
        for s in batch.sources:
            if s.source_document_id:
                m = dict(doc_meta.get(s.source_document_id) or {})
            elif s.source_audio_id:
                m = dict(audio_meta.get(s.source_audio_id) or {})
            else:
                continue
            if _segment_label(m, gb) == seg:
                n += 1
        return n

    if gb == "interview_unit":
        ic_a = _ic_interview_unit(ra or "")
        ic_b = _ic_interview_unit(rb or "")
    else:
        ic_a = _ic_for(ra)
        ic_b = _ic_for(rb)
    if ic_a < 1 or ic_b < 1:
        raise ValueError("segment_no_interviews")

    side_a = _merge_dashboard_block(ra, block_a, ic_a)
    side_b = _merge_dashboard_block(rb, block_b, ic_b)

    lang = (output_language or "ru").strip().lower()

    portrait_a, portrait_b = await asyncio.gather(
        get_or_create_audience_portrait_response(
            session, batch, group_by=gb, segment_value=ra, output_language=lang, recalculate=False, settings=st
        ),
        get_or_create_audience_portrait_response(
            session, batch, group_by=gb, segment_value=rb, output_language=lang, recalculate=False, settings=st
        ),
    )
    ctx_a, ctx_b = await asyncio.gather(
        build_portrait_context(session, batch, group_by=gb, segment_value=ra),
        build_portrait_context(session, batch, group_by=gb, segment_value=rb),
    )

    strategy_a, strategy_b = await asyncio.gather(
        get_or_create_pr_strategy_response(
            session,
            batch,
            group_by=gb,
            segment_value=ra,
            output_language=lang,
            recalculate=False,
            settings=st,
            prefetched_context=ctx_a,
            prefetched_portrait=portrait_a.portrait.model_dump(),
        ),
        get_or_create_pr_strategy_response(
            session,
            batch,
            group_by=gb,
            segment_value=rb,
            output_language=lang,
            recalculate=False,
            settings=st,
            prefetched_context=ctx_b,
            prefetched_portrait=portrait_b.portrait.model_dump(),
        ),
    )

    side_a["audience_portrait_summary"] = _portrait_summary(portrait_a)
    side_a["pr_strategy_summary"] = _strategy_summary(strategy_a)
    side_b["audience_portrait_summary"] = _portrait_summary(portrait_b)
    side_b["pr_strategy_summary"] = _strategy_summary(strategy_b)

    differences, pr_implications = _build_differences_and_pr(
        side_a=side_a,
        side_b=side_b,
        portrait_a=portrait_a,
        portrait_b=portrait_b,
        strategy_a=strategy_a,
        strategy_b=strategy_b,
        lang=lang,
    )

    llm_actions: list[dict[str, Any]] = []
    llm_alerts: list[dict[str, Any]] = []
    try:
        raw_cmp = await asyncio.to_thread(
            generate_compare_decision_layer_sync,
            segment_a=ra,
            segment_b=rb,
            differences=differences,
            pr_implications=pr_implications,
            strategy_a=strategy_a.model_dump(mode="json"),
            strategy_b=strategy_b.model_dump(mode="json"),
            output_language=lang,
            settings=st,
        )
        llm_actions = list(raw_cmp.get("priority_actions") or [])
        llm_alerts = list(raw_cmp.get("alerts") or [])
    except Exception:
        logger.exception("segment compare decision LLM failed batch_id=%s", batch.id)

    if not llm_actions:
        llm_actions = fallback_compare_priority_actions(
            pr_implications, differences, output_language=lang
        )
    heur_cmp = heuristic_alerts_segment_compare(
        side_a=side_a,
        side_b=side_b,
        segment_a=ra,
        segment_b=rb,
        output_language=lang,
    )
    merged_alerts = merge_alerts(llm_alerts, heur_cmp)
    dl = build_compare_decision_payload(priority_actions=llm_actions, alerts=merged_alerts)

    return {
        "group_by": gb,
        "segment_a": side_a,
        "segment_b": side_b,
        "differences": differences,
        "pr_implications": pr_implications,
        **dl,
        "meta": {
            "segment_a_resolved": ra,
            "segment_b_resolved": rb,
            "output_language": lang,
        },
    }
