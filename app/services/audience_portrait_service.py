"""Audience Portrait: LLM synthesis from batch aggregates, metadata, and entity quotes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntityType
from app.infrastructure.llm_http import httpx_timeout_for_upstream_read
from app.infrastructure.settings import Settings, get_settings
from app.models.extracted_entity import ExtractedEntity
from app.models.research_batch import ResearchBatch
from app.models.transcript import Transcript
from app.services.batch_corpus_service import text_chunks_scope_and
from app.repositories.interview_unit_repository import count_units_for_documents
from app.services.data_readiness_service import (
    assess_strict_pr_readiness,
    assess_synthesis_readiness,
    insufficient_synthesis_message,
)
from app.services.evidence_driven_bundle import (
    dashboard_empty_for_llm,
    dashboard_first_bundle,
    insufficient_data_payload,
    insufficient_missing_from_readiness,
)
from app.services.research_batch_dashboard_service import (
    DASHBOARD_GROUP_BY_FIELDS,
    _aggregate_entities_block,
    _audience_snapshot_from_metas,
    _build_pr_insight_rollups,
    _entity_quote,
    _load_metadata_maps,
    _meta_for_entity,
    _segment_label,
    _word_frequency_for_chunk_filter,
)

logger = logging.getLogger(__name__)

_QUOTE_ENTITY_TYPES = frozenset(
    {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.TRUST_ISSUE,
        EntityType.SENTIMENT_SIGNAL,
        EntityType.RISK,
        EntityType.BEHAVIOR_PATTERN,
        EntityType.ADOPTION_BARRIER,
    }
)

_MAX_ENTITIES_LOAD = 4000
_MAX_QUOTES = 64
_MAX_QUOTE_CHARS = 380


def _quote_source_bucket(q: dict[str, Any]) -> str:
    if q.get("source_document_id"):
        return f"d:{q['source_document_id']}"
    if q.get("source_audio_id"):
        return f"a:{q['source_audio_id']}"
    if q.get("transcript_id"):
        return f"t:{q['transcript_id']}"
    return "z:unknown"


def _stratify_quotes_by_source(items: list[dict[str, Any]], *, max_total: int) -> list[dict[str, Any]]:
    from collections import defaultdict

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in items:
        buckets[_quote_source_bucket(q)].append(q)
    keys = sorted(buckets.keys(), key=lambda k: (k.startswith("z:"), k))
    out: list[dict[str, Any]] = []
    round_idx = 0
    while len(out) < max_total:
        progressed = False
        for k in keys:
            lst = buckets[k]
            if round_idx < len(lst):
                out.append(lst[round_idx])
                progressed = True
                if len(out) >= max_total:
                    break
        if not progressed:
            break
        round_idx += 1
    return out


def _build_interview_evidence_summaries(
    entities: list[ExtractedEntity],
    doc_ids: list[UUID],
    audio_ids: list[UUID],
    *,
    limit_topics: int = 3,
    max_items: int = 24,
) -> list[dict[str, Any]]:
    from collections import Counter, defaultdict

    titles_by_key: dict[str, Counter[str]] = defaultdict(Counter)

    def _ent_bucket(e: ExtractedEntity) -> str:
        if e.source_document_id:
            return f"d:{e.source_document_id}"
        if e.source_audio_id:
            return f"a:{e.source_audio_id}"
        if e.transcript_id:
            return f"t:{e.transcript_id}"
        return ""

    for e in entities:
        lab = (e.title or "").strip()[:220]
        if not lab:
            continue
        bk = _ent_bucket(e)
        if bk:
            titles_by_key[bk][lab] += 1

    out: list[dict[str, Any]] = []
    for did in doc_ids:
        top = titles_by_key[f"d:{did}"].most_common(limit_topics)
        out.append(
            {
                "source_kind": "document",
                "source_document_id": str(did),
                "top_signals": [t for t, _c in top],
            }
        )
    for aid in audio_ids:
        top = titles_by_key[f"a:{aid}"].most_common(limit_topics)
        out.append({"source_kind": "audio", "source_audio_id": str(aid), "top_signals": [t for t, _c in top]})
    return out[:max_items]


def _system_prompt(output_language: str) -> str:
    if output_language == "uz":
        return (
            "Siz tadqiqot portreti bo'yicha tahlilchisiz. Faqat berilgan JSON ma'lumotlariga tayangan holda "
            "auditoriya xatti-harakati, qarorlar va nutq uslubi haqida aniq, tekshiriladigan gaplar yozing. "
            "Umumiy marketing jumlalarisiz. Har bir maydon 2–6 jumladan iborat bo'lishi mumkin. "
            "Barcha javoblar oʻzbek tilida. Faqat bitta JSON obyekt qaytaring (schema user xabarida)."
        )
    if output_language == "en":
        return (
            "You are a research analyst writing an audience portrait. Ground every statement in the provided "
            "JSON evidence (topics, problems, risks, patterns, quotes, metadata). Avoid generic marketing language. "
            "Each field: 2–6 sentences, concrete behaviors and motivations. Output language: English. "
            "Return a single JSON object only (schema in user message)."
        )
    return (
        "Ты аналитик качественных исследований. Пишешь портрет аудитории строго по переданным данным "
        "(темы, проблемы, риски, паттерны, цитаты, метаданные). Запрещены общие фразы без опоры на вход — "
        "каждый абзац должен ссылаться на реальные паттерны из данных. Поля: по 2–6 предложений, конкретика. "
        "Язык ответа: русский. Верни один JSON-объект (схема в user-сообщении)."
    )


def _user_payload(
    *,
    batch_name: str,
    output_language: str,
    context: dict[str, Any],
) -> str:
    schema_hint = {
        "decision_making": "str",
        "fears": "str",
        "trust_drivers": "str",
        "pain_points": "str",
        "language_style": "str",
        "brand_perception": "str",
        "emotional_triggers": "str",
    }
    if output_language == "ru":
        instr = (
            "Свяжи выводы с именами тем/проблем из evidence, не выдумывай новые факты. "
            "Если данных мало, честно укажи ограниченность выборки внутри полей (кратко)."
        )
    elif output_language == "uz":
        instr = (
            "Xulosalarni evidence dagi mavzular/muammolar bilan bog'lang; kam ma'lumot bo'lsa, "
            "cheklovlarni qisqa ayting."
        )
    else:
        instr = "Tie claims to evidence; if data is thin, note limitations briefly inside the fields."

    body = {
        "task": "audience_portrait",
        "output_language": output_language,
        "study_name": batch_name,
        "evidence": context,
        "required_json_keys": list(schema_hint.keys()),
        "instructions": instr,
    }
    return json.dumps(body, ensure_ascii=False)[:95_000]


def _static_portrait_blocked(message: str) -> dict[str, str]:
    return {
        "decision_making": message,
        "fears": message,
        "trust_drivers": message,
        "pain_points": message,
        "language_style": message,
        "brand_perception": message,
        "emotional_triggers": message,
    }


def _map_quotes_to_portrait_fields(
    quotes: list[dict[str, Any]], *, per_field: int = 4
) -> dict[str, list[dict[str, Any]]]:
    """Deterministic: map entity-backed quotes to portrait field keys (data-first traceability)."""
    fmap: dict[str, set[EntityType]] = {
        "decision_making": {
            EntityType.BEHAVIOR_PATTERN,
            EntityType.OPEN_QUESTION,
            EntityType.HYPOTHESIS,
            EntityType.ADOPTION_BARRIER,
        },
        "fears": {EntityType.RISK, EntityType.PAIN_POINT, EntityType.ADOPTION_BARRIER, EntityType.TRUST_ISSUE},
        "trust_drivers": {EntityType.TRUST_ISSUE, EntityType.SENTIMENT_SIGNAL, EntityType.BEHAVIOR_PATTERN},
        "pain_points": {
            EntityType.PROBLEM,
            EntityType.PAIN_POINT,
            EntityType.USER_NEED,
            EntityType.ADOPTION_BARRIER,
        },
        "language_style": {EntityType.SENTIMENT_SIGNAL, EntityType.BEHAVIOR_PATTERN, EntityType.USER_NEED},
        "brand_perception": {EntityType.TRUST_ISSUE, EntityType.RECOMMENDATION, EntityType.SENTIMENT_SIGNAL},
        "emotional_triggers": {EntityType.SENTIMENT_SIGNAL, EntityType.RISK, EntityType.PROBLEM, EntityType.PAIN_POINT},
    }
    by_field: dict[str, list[dict[str, Any]]] = {k: [] for k in fmap}
    for q in quotes:
        try:
            ety = EntityType(str(q.get("type") or ""))
        except Exception:
            continue
        for field, typeset in fmap.items():
            if ety in typeset and len(by_field[field]) < 5:
                by_field[field].append(
                    {
                        "insight": (q.get("title") or "")[:200],
                        "evidence": [
                            {
                                "quote": (q.get("text") or "")[:420],
                                "entity_id": q.get("entity_id"),
                                "source_document_id": q.get("source_document_id"),
                                "transcript_id": q.get("transcript_id"),
                                "source_audio_id": q.get("source_audio_id"),
                            }
                        ],
                    }
                )
    return {k: v[:per_field] for k, v in by_field.items()}


def _parse_portrait_json(raw: str) -> dict[str, str]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("portrait_not_object")
    keys = (
        "decision_making",
        "fears",
        "trust_drivers",
        "pain_points",
        "language_style",
        "brand_perception",
        "emotional_triggers",
    )
    out: dict[str, str] = {}
    for k in keys:
        v = data.get(k)
        out[k] = str(v).strip() if v is not None else ""
    return out


def _generate_sync(user_message: str, output_language: str, settings: Settings) -> dict[str, str]:
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError("openai_api_key_missing")
    read_s = max(120.0, float(settings.openai_http_timeout_seconds))
    client = OpenAI(api_key=key, timeout=httpx_timeout_for_upstream_read(read_seconds=read_s))
    completion = client.chat.completions.create(
        model=settings.openai_summary_model,
        messages=[
            {"role": "system", "content": _system_prompt(output_language)},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.35,
    )
    raw = completion.choices[0].message.content if completion.choices else None
    if not raw:
        raise ValueError("empty_llm_response")
    return _parse_portrait_json(raw)


async def build_portrait_context(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None,
    segment_value: str | None,
) -> dict[str, Any]:
    doc_ids = [s.source_document_id for s in batch.sources if s.source_document_id]
    audio_ids = [s.source_audio_id for s in batch.sources if s.source_audio_id]
    transcript_ids: list[UUID] = []
    if audio_ids:
        tid_stmt = select(Transcript.id).where(Transcript.source_audio_id.in_(audio_ids))
        transcript_ids = list((await session.scalars(tid_stmt)).all())

    doc_meta, audio_meta, transcript_to_audio = await _load_metadata_maps(session, doc_ids, audio_ids)

    metas_all: list[dict[str, Any]] = []
    for did in doc_ids:
        metas_all.append(dict(doc_meta.get(did) or {}))
    for aid in audio_ids:
        metas_all.append(dict(audio_meta.get(aid) or {}))

    metas_filtered: list[dict[str, Any]] = []
    if group_by and segment_value and group_by in DASHBOARD_GROUP_BY_FIELDS:
        for did in doc_ids:
            m = dict(doc_meta.get(did) or {})
            if _segment_label(m, group_by) == segment_value:
                metas_filtered.append(m)
        for aid in audio_ids:
            m = dict(audio_meta.get(aid) or {})
            if _segment_label(m, group_by) == segment_value:
                metas_filtered.append(m)
        audience_snapshot = _audience_snapshot_from_metas(metas_filtered)
    else:
        audience_snapshot = _audience_snapshot_from_metas(metas_all)

    if not doc_ids and not audio_ids:
        return {
            "interview_count": 0,
            "audience_snapshot": audience_snapshot,
            "topics_pie": [],
            "problems_bar": [],
            "risks_bar": [],
            "word_frequency": [],
            "sentiment": {"positive_signals": 0, "negative_signals": 0, "balance": "unknown"},
            "top_patterns": [],
            "top_insights": [],
            "quotes": [],
            "interview_evidence_summaries": [],
            "entity_row_count": 0,
            "evidence_quotes_count": 0,
        }

    parts: list[Any] = []
    if doc_ids:
        parts.append(ExtractedEntity.source_document_id.in_(doc_ids))
    if audio_ids:
        parts.append(ExtractedEntity.source_audio_id.in_(audio_ids))
    if transcript_ids:
        parts.append(ExtractedEntity.transcript_id.in_(transcript_ids))

    surface_filter = or_(*parts)
    ent_stmt = (
        select(ExtractedEntity)
        .where(
            ExtractedEntity.project_id == batch.project_id,
            ExtractedEntity.canonical_entity_id.is_(None),
            surface_filter,
        )
        .order_by(ExtractedEntity.created_at.asc())
        .limit(_MAX_ENTITIES_LOAD)
    )
    entities = list((await session.scalars(ent_stmt)).all())

    if group_by and segment_value and group_by in DASHBOARD_GROUP_BY_FIELDS:
        entities = [
            e
            for e in entities
            if _segment_label(
                _meta_for_entity(e, doc_meta=doc_meta, audio_meta=audio_meta, transcript_to_audio=transcript_to_audio),
                group_by,
            )
            == segment_value
        ]

    agg = _aggregate_entities_block(entities)

    doc_in_seg: set[UUID] = set(doc_ids)
    audio_in_seg: set[UUID] = set(audio_ids)
    if group_by and segment_value and group_by in DASHBOARD_GROUP_BY_FIELDS:
        doc_in_seg = {did for did in doc_ids if _segment_label(dict(doc_meta.get(did) or {}), group_by) == segment_value}
        audio_in_seg = {aid for aid in audio_ids if _segment_label(dict(audio_meta.get(aid) or {}), group_by) == segment_value}
    tr_in_seg = [tid for tid, a in transcript_to_audio.items() if a in audio_in_seg]
    chunk_scope = text_chunks_scope_and(
        batch.project_id,
        document_ids=list(doc_in_seg),
        audio_ids=list(audio_in_seg),
        transcript_ids=tr_in_seg,
    )
    wf = await _word_frequency_for_chunk_filter(session, chunk_scope, limit=36)

    quote_candidates: list[dict[str, Any]] = []
    for e in entities:
        if e.entity_type not in _QUOTE_ENTITY_TYPES:
            continue
        text = _entity_quote(e, max_len=_MAX_QUOTE_CHARS)
        if len(text) < 12:
            continue
        q: dict[str, Any] = {
            "type": e.entity_type.value,
            "title": (e.title or "")[:220],
            "text": text[:_MAX_QUOTE_CHARS],
            "entity_id": str(e.id),
        }
        if e.source_document_id:
            q["source_document_id"] = str(e.source_document_id)
        if e.source_audio_id:
            q["source_audio_id"] = str(e.source_audio_id)
        if e.transcript_id:
            q["transcript_id"] = str(e.transcript_id)
        if e.chunk_id:
            q["chunk_id"] = str(e.chunk_id)
        meta_e = _meta_for_entity(e, doc_meta=doc_meta, audio_meta=audio_meta, transcript_to_audio=transcript_to_audio)
        seg_obj = {k: _segment_label(meta_e, k) for k in DASHBOARD_GROUP_BY_FIELDS}
        seg_obj = {k: v for k, v in seg_obj.items() if v and v != "unknown"}
        if seg_obj:
            q["segment"] = seg_obj
        quote_candidates.append(q)

    quotes = _stratify_quotes_by_source(quote_candidates, max_total=_MAX_QUOTES)

    interview_evidence_summaries = _build_interview_evidence_summaries(entities, doc_ids, audio_ids)

    pr_insight_rollups = _build_pr_insight_rollups(
        entities,
        doc_meta=doc_meta,
        audio_meta=audio_meta,
        transcript_to_audio=transcript_to_audio,
        limit_groups=18,
    )

    if group_by and segment_value and group_by in DASHBOARD_GROUP_BY_FIELDS:
        base_ic = len(metas_filtered)
    else:
        base_ic = len(metas_all)

    use_units = getattr(batch, "single_file_multi_interview_mode", True)
    uid_n = await count_units_for_documents(session, doc_ids) if doc_ids else 0
    if use_units and uid_n > 0:
        interview_count = uid_n + len(audio_ids)
    else:
        interview_count = base_ic
    audience_snapshot["interview_count"] = interview_count

    evidence_quotes_count = 0
    for e in entities:
        ev = dict(e.evidence_json or {})
        q = str(ev.get("quote") or "").strip()
        body = (e.content or "").strip()
        if len(q) >= 8 or len(body) >= 12:
            evidence_quotes_count += 1

    return {
        "interview_count": interview_count,
        "audience_snapshot": audience_snapshot,
        "topics_pie": agg["topics_pie"][:15],
        "problems_bar": agg["problems_bar"][:15],
        "risks_bar": agg["risks_bar"][:12],
        "word_frequency": wf[:30],
        "sentiment": agg["sentiment"],
        "top_patterns": agg["top_patterns"][:12],
        "top_insights": agg["top_insights"][:18],
        "pr_insight_rollups": pr_insight_rollups,
        "quotes": quotes,
        "interview_evidence_summaries": interview_evidence_summaries,
        "entity_row_count": len(entities),
        "evidence_quotes_count": evidence_quotes_count,
    }


def run_portrait_generation_sync(
    context: dict[str, Any],
    *,
    batch_name: str,
    output_language: str,
    settings: Settings,
) -> dict[str, str]:
    """Run the audience-portrait LLM on a pre-built evidence context (used by PR strategy pipeline)."""
    user_msg = _user_payload(batch_name=batch_name, output_language=output_language, context=context)
    return _generate_sync(user_msg, output_language, settings)


async def generate_audience_portrait(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None,
    segment_value: str | None,
    output_language: str,
    settings: Settings | None = None,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    st = settings or get_settings()
    ctx = await build_portrait_context(session, batch, group_by=group_by, segment_value=segment_value)
    ctx["__output_language"] = output_language
    dash_snap = dashboard_first_bundle(ctx)
    empty_llm, missing_dash = dashboard_empty_for_llm(ctx)
    if empty_llm:
        readiness0 = assess_synthesis_readiness(ctx, output_language=output_language)
        ins = insufficient_data_payload(output_language, missing_dash)
        portrait = _static_portrait_blocked(ins["message"])
        p_grounding = {k: [] for k in portrait}
        meta = {
            "interview_count": ctx["interview_count"],
            "group_by": group_by,
            "segment_value": segment_value,
            "topics_in_prompt": len(ctx.get("topics_pie") or []),
            "quotes_in_prompt": len(ctx.get("quotes") or []),
            "output_language": output_language,
            "synthesis_blocked": True,
            "data_coverage_score": readiness0.data_coverage_score,
            "portrait_grounding": p_grounding,
            "data_quality_warnings": list(dict.fromkeys([*(readiness0.warnings or []), ins["message"]])),
            "data_quality_message": ins["message"],
            "strict_pr_ready": False,
            "gates_checklist": [],
            "dashboard_snapshot": dash_snap,
            "insufficient_data": ins,
        }
        return portrait, meta, ctx
    strict = assess_strict_pr_readiness(ctx, output_language=output_language)
    readiness = assess_synthesis_readiness(ctx, output_language=output_language)
    if not readiness.can_synthesize or not strict.ready:
        msg = (
            strict.user_message
            if not strict.ready
            else insufficient_synthesis_message(output_language)
        )
        portrait = _static_portrait_blocked(msg)
        p_grounding = {k: [] for k in portrait}
        miss = insufficient_missing_from_readiness(
            strict_ready=strict.ready,
            strict_checklist=list(strict.checklist),
            can_synthesize=readiness.can_synthesize,
        )
        ins = insufficient_data_payload(output_language, miss or ["unknown"])
        meta = {
            "interview_count": ctx["interview_count"],
            "group_by": group_by,
            "segment_value": segment_value,
            "topics_in_prompt": len(ctx.get("topics_pie") or []),
            "quotes_in_prompt": len(ctx.get("quotes") or []),
            "output_language": output_language,
            "synthesis_blocked": True,
            "data_coverage_score": readiness.data_coverage_score,
            "portrait_grounding": p_grounding,
            "data_quality_warnings": list(
                dict.fromkeys([*(readiness.warnings or []), *( [strict.user_message] if strict.user_message else [])]),
            ),
            "data_quality_message": msg,
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
        return portrait, meta, ctx
    try:
        portrait = await asyncio.to_thread(
            run_portrait_generation_sync,
            ctx,
            batch_name=batch.name or "",
            output_language=output_language,
            settings=st,
        )
    except Exception:
        logger.exception("audience_portrait LLM failed batch_id=%s", batch.id)
        raise
    p_grounding = _map_quotes_to_portrait_fields(list(ctx.get("quotes") or []))
    r2 = assess_synthesis_readiness(ctx, output_language=output_language)
    strict_ok = assess_strict_pr_readiness(ctx, output_language=output_language)
    meta = {
        "interview_count": ctx["interview_count"],
        "group_by": group_by,
        "segment_value": segment_value,
        "topics_in_prompt": len(ctx.get("topics_pie") or []),
        "quotes_in_prompt": len(ctx.get("quotes") or []),
        "output_language": output_language,
        "synthesis_blocked": False,
        "data_coverage_score": r2.data_coverage_score,
        "portrait_grounding": p_grounding,
        "data_quality_warnings": r2.warnings,
        "data_quality_message": None,
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
        "dashboard_snapshot": dashboard_first_bundle(ctx),
    }
    return portrait, meta, ctx
