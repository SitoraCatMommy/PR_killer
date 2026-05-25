"""Multi-source analytics for a research batch (study); optional segment breakdown via source metadata_json."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.domain.enums import EntityType, JobStatus
from app.domain.pr_signals import taxonomy_label_for_entity
from app.infrastructure.settings import get_settings
from app.services.batch_dashboard_pr import (
    EMPTY_TIMELINE_REAL,
    corpus_tokens,
    entity_matches_date_filter,
    narrow_source_ids,
    ngram_counts,
    parse_iso_date,
    pr_signal_tag_integrity,
    pr_taxonomy_totals,
    risk_heatmap,
    segment_compare_pr_bars,
    sentiment_stacked_from_breakdown,
    timeline_series_real,
    tokenize_corpus,
)
from app.models.extracted_entity import ExtractedEntity
from app.models.project import Project
from app.models.research_batch import ResearchBatch
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.repositories.interview_unit_repository import count_units_for_documents, list_units_for_documents
from app.services.batch_corpus_service import resolve_transcript_ids_async, text_chunks_scope_and
from app.services.custdev_report_bundle import build_insight_graph_v1
from app.services.pr_lexicon_signals import build_pr_lexicon_signals_from_chunks
from app.services.data_readiness_service import (
    assess_synthesis_readiness,
    assess_strict_pr_readiness,
    build_data_warnings,
)

_TOKEN_RE = re.compile(r"[\wа-яёА-ЯЁ]+", re.UNICODE)

PR_SYNTHESIS_INSIGHT_TYPES = frozenset(
    {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.BEHAVIOR_PATTERN,
        EntityType.TRUST_ISSUE,
        EntityType.ADOPTION_BARRIER,
        EntityType.RISK,
        EntityType.HYPOTHESIS,
        EntityType.OPEN_QUESTION,
        EntityType.SENTIMENT_SIGNAL,
    }
)

_TOPIC_TYPES = frozenset(
    {
        EntityType.TOPIC,
        EntityType.HYPOTHESIS,
        EntityType.OPEN_QUESTION,
    }
)
_PROBLEM_TYPES = frozenset(
    {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.ADOPTION_BARRIER,
    }
)
_PATTERN_TYPES = frozenset(
    {
        EntityType.BEHAVIOR_PATTERN,
        EntityType.SENTIMENT_SIGNAL,
        EntityType.TRUST_ISSUE,
    }
)
_RISK_TYPES = frozenset({EntityType.RISK, EntityType.TRUST_ISSUE})
_SENT_POS = frozenset({EntityType.SENTIMENT_SIGNAL, EntityType.TRUST_ISSUE})
_SENT_NEG = frozenset({EntityType.RISK, EntityType.PROBLEM, EntityType.PAIN_POINT})

DASHBOARD_GROUP_BY_FIELDS = frozenset(
    {
        "gender",
        "age_range",
        "segments",
        "language",
        "city",
        "interview_type",
        "source",
        "date",
        "interview_unit",
    }
)

_AUDIO_EXTS = frozenset(
    {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".webm", ".wma", ".aiff", ".caf"}
)


def _pipeline_phase(pipeline: dict[str, Any] | None) -> str:
    p = pipeline or {}
    return str(p.get("phase") or p.get("stage") or "").strip().lower()


async def _count_chunks_for_scope(session: AsyncSession, chunk_scope: ColumnElement) -> int:
    return int(await session.scalar(select(func.count()).select_from(TextChunk).where(chunk_scope)) or 0)


def _build_data_readiness_diagnostics(
    *,
    interviews_total: int,
    interviews_documents_ready: int,
    transcripts_completed: int,
    chunks_total: int,
    entities_total: int,
    quotes_total: int,
    doc_rows: list[dict[str, Any]],
    audio_scope_count: int,
    base_block: dict[str, Any],
) -> dict[str, Any]:
    missing: list[str] = []
    if interviews_total < 1 and audio_scope_count < 1 and not doc_rows:
        missing.append("no_batch_sources")
    if chunks_total < 1 and (doc_rows or audio_scope_count > 0):
        missing.append("chunking_not_run_or_empty_corpus")
    if chunks_total > 0 and entities_total < 1:
        missing.append("no_entities")
    entity_extraction_gap = bool(chunks_total > 0 and entities_total < 1)
    if entities_total > 0 and not (base_block.get("topics_pie") or []):
        missing.append("no_typed_topic_labels")
    risk_rows = base_block.get("risks_bar") or []
    risk_mass = sum(int(x.get("value") or 0) for x in risk_rows)
    if entities_total > 2 and risk_mass < 1:
        missing.append("low_risk_signals")
    ext_errors = [
        str((r.get("pipeline") or {}).get("extraction", {}).get("status") or "")
        for r in doc_rows
        if isinstance((r.get("pipeline") or {}).get("extraction"), dict)
    ]
    if any(x in ("chunk_failed", "extraction_failed") for x in ext_errors):
        missing.append("pipeline_errors_on_documents")
    if any(_pipeline_phase(r.get("pipeline")) in ("uploaded",) for r in doc_rows):
        missing.append("documents_not_chunked")
    pipelines_still_running = False
    if doc_rows:
        ready = interviews_documents_ready
        if ready < len(doc_rows):
            pipelines_still_running = True
    if audio_scope_count > 0 and transcripts_completed < audio_scope_count:
        pipelines_still_running = True

    return {
        "interviews_total": int(interviews_total),
        "interviews_processed": int(min(interviews_total, interviews_documents_ready + transcripts_completed)),
        "documents_ready": int(interviews_documents_ready),
        "transcripts_completed": int(transcripts_completed),
        "entities_total": int(entities_total),
        "chunks_total": int(chunks_total),
        "quotes_total": int(quotes_total),
        "missing_steps": missing,
        "pipelines_still_running": pipelines_still_running,
        "entity_extraction_gap": entity_extraction_gap,
        "visualization_note": (
            "Недостаточно извлечённых сущностей для визуализации"
            if entities_total < 1
            else (
                "Сущности есть, но мало PR-рисковых сигналов — проверьте типизацию извлечения"
                if "low_risk_signals" in missing
                else ""
            )
        ),
    }


def _tokenize_corpus(text: str, limit: int = 400, *, apply_stopwords: bool = False) -> list[tuple[str, int]]:
    return tokenize_corpus(text, limit, apply_stopwords=apply_stopwords)


def _segment_label(meta: dict[str, Any], group_by: str) -> str:
    raw = meta.get(group_by)
    if raw is None:
        return "unknown"
    if isinstance(raw, list):
        inner = [str(x).strip() for x in raw if str(x).strip()]
        return ", ".join(sorted(inner)) if inner else "unknown"
    if isinstance(raw, dict) and group_by == "age_range":
        lo = raw.get("min") or raw.get("from")
        hi = raw.get("max") or raw.get("to")
        if lo is not None and hi is not None:
            return f"{lo}-{hi}"
        if raw:
            return ", ".join(f"{k}:{v}" for k, v in list(raw.items())[:6] if v is not None) or "unknown"
    s = str(raw).strip()
    if s in ("[object Object]", "[object object]") or (isinstance(s, str) and s.startswith("[object ")):
        return "unknown"
    return s if s else "unknown"


def _meta_for_entity(
    e: ExtractedEntity,
    *,
    doc_meta: dict[UUID, dict[str, Any]],
    audio_meta: dict[UUID, dict[str, Any]],
    transcript_to_audio: dict[UUID, UUID],
) -> dict[str, Any]:
    if e.source_document_id:
        return dict(doc_meta.get(e.source_document_id) or {})
    if e.source_audio_id:
        return dict(audio_meta.get(e.source_audio_id) or {})
    if e.transcript_id:
        aid = transcript_to_audio.get(e.transcript_id)
        return dict(audio_meta.get(aid) or {}) if aid else {}
    return {}


def _bar_rows_with_pct(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(int(x.get("value") or 0) for x in rows) or 1
    return [{**x, "pct": round(100.0 * int(x.get("value") or 0) / total, 1)} for x in rows]


def _sentiment_with_fractions(sent: dict[str, Any]) -> dict[str, Any]:
    pos = int(sent.get("positive_signals") or 0)
    neg = int(sent.get("negative_signals") or 0)
    tot = pos + neg
    if tot < 1:
        return {**sent, "positive_pct": 0.0, "negative_pct": 0.0, "neutralish_pct": 0.0}
    rem = 100.0 - (100.0 * pos / tot) - (100.0 * neg / tot)
    return {
        **sent,
        "positive_pct": round(100.0 * pos / tot, 1),
        "negative_pct": round(100.0 * neg / tot, 1),
        "neutralish_pct": round(max(0.0, rem), 1),
    }


def _entity_quote(e: ExtractedEntity, *, max_len: int = 360) -> str:
    ev = dict(e.evidence_json or {})
    q = str(ev.get("quote") or "").strip()
    if not q:
        q = (e.content or "").strip()
    q = " ".join(q.split())
    return q[:max_len]


def _human_insight_text(e: ExtractedEntity, label: str, pr_signal: str) -> str:
    """Turn an extracted label into a short analyst-style sentence grounded in the respondent wording."""
    quote = _entity_quote(e, max_len=220)
    clean_label = " ".join((label or "").split()).strip(" .")
    if not clean_label:
        clean_label = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
    if quote and quote.lower() != clean_label.lower():
        return f"В интервью повторяется сигнал «{clean_label}»: респондент формулирует это так — «{quote}»."
    return f"В интервью повторяется сигнал «{clean_label}» в зоне «{pr_signal}»."


def _build_pr_insight_rollups(
    entities: list[ExtractedEntity],
    *,
    doc_meta: dict[UUID, dict[str, Any]],
    audio_meta: dict[UUID, dict[str, Any]],
    transcript_to_audio: dict[UUID, UUID],
    limit_groups: int = 40,
) -> list[dict[str, Any]]:
    """PR taxonomy rollups: count, 2–5 quotes, source ids, segment tags; mark insufficient when <2 quotes."""
    groups: dict[tuple[str, str], list[ExtractedEntity]] = defaultdict(list)
    for e in entities:
        tax = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        label = (e.title or "").strip()[:200] or (e.content or "").strip()[:120] or "—"
        groups[(tax, label)].append(e)

    out: list[dict[str, Any]] = []
    for (tax, label), elist in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:limit_groups]:
        quotes: list[str] = []
        source_ids: list[str] = []
        seg_tags: set[str] = set()
        for x in elist:
            source_ids.append(str(x.id))
            if x.source_document_id:
                source_ids.append(f"doc:{x.source_document_id}")
            ev = dict(x.evidence_json or {})
            q = str(ev.get("quote") or "").strip()
            if not q and (x.content or "").strip():
                q = (x.content or "").strip()[:400]
            if len(q) >= 8:
                quotes.append(q[:500])
            m = _meta_for_entity(x, doc_meta=doc_meta, audio_meta=audio_meta, transcript_to_audio=transcript_to_audio)
            for k in ("gender", "age_range", "segments", "city", "language"):
                v = m.get(k)
                if v is None:
                    continue
                if isinstance(v, list):
                    for it in v[:6]:
                        seg_tags.add(f"{k}:{it}")
                else:
                    seg_tags.add(f"{k}:{v}")
            if len(quotes) >= 5:
                break
        quotes = quotes[:5]
        ev_ok = len(quotes) >= 2
        out.append(
            {
                "insight_label": label,
                "taxonomy": tax,
                "pr_signal_type": tax,
                "count": len(elist),
                "quotes": quotes,
                "source_ids": source_ids[:24],
                "segment_tags": sorted(seg_tags)[:20],
                "evidence_status": "ok" if ev_ok else "insufficient_evidence",
            }
        )
    return out


def _t_quality_note(n_ent: int, n_quotes: int) -> str:
    if n_ent < 15:
        return "Мало извлечённых единиц — дождитесь завершения извлечения по всем файлам."
    if n_quotes < 8:
        return "Мало цитат с явным evidence — проверьте качество транскриптов и чанков."
    return "Извлечение в допустимых пределах для PR-слоя (при соблюдении чеклиста объёма)."


def _traceability_rows(
    entities: list[ExtractedEntity],
    _doc_meta: dict[UUID, dict[str, Any]],
    _audio_meta: dict[UUID, dict[str, Any]],
    _transcript_to_audio: dict[UUID, UUID],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for e in entities[:limit]:
        ev = dict(e.evidence_json or {})
        quote = str(ev.get("quote") or "").strip() or (e.content or "").strip()[:360]
        tax = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        src: list[str] = [str(e.id)]
        if e.source_document_id:
            src.append(f"doc:{e.source_document_id}")
        if e.chunk_id:
            src.append(f"chunk:{e.chunk_id}")
        nav: dict[str, Any] | None = None
        if e.source_document_id:
            nav = {
                "kind": "document",
                "project_id": str(e.project_id),
                "document_id": str(e.source_document_id),
                "chunk_id": str(e.chunk_id),
            }
        rows.append(
            {
                "insight_label": (e.title or "")[:220] or (e.content or "")[:120],
                "pr_signal_type": tax,
                "entity_type": e.entity_type.value,
                "count": 1,
                "source_ids": src,
                "sample_quote": quote[:500],
                "open_source_link": nav,
            }
        )
    return rows


def _traced_labels(entities: list[ExtractedEntity], etypes: set[EntityType], *, limit: int = 20) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[ExtractedEntity]] = defaultdict(list)
    for e in entities:
        if e.entity_type not in etypes:
            continue
        title = (e.title or "").strip()[:200]
        if len(title) < 3:
            continue
        pr_sig = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        k = (e.entity_type.value, title, pr_sig)
        if len(groups[k]) < 64:
            groups[k].append(e)
    out: list[dict[str, Any]] = []
    for (et, title, pr_sig), elist in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:limit]:
        srcs: list[dict[str, Any]] = []
        for x in elist[:32]:
            evj: dict[str, Any] = dict(x.evidence_json or {})
            char_off = evj.get("char_start")
            if char_off is None and isinstance(evj.get("span"), dict):
                char_off = (evj.get("span") or {}).get("start")
            ref: dict[str, Any] = {
                "entity_id": str(x.id),
                "project_id": str(x.project_id),
                "source_document_id": str(x.source_document_id) if x.source_document_id else None,
                "source_audio_id": str(x.source_audio_id) if x.source_audio_id else None,
                "transcript_id": str(x.transcript_id) if x.transcript_id else None,
                "chunk_id": str(x.chunk_id),
            }
            if char_off is not None:
                ref["char_offset"] = int(char_off) if str(char_off).isdigit() else char_off
            tj: dict[str, Any] = dict(x.tags_json or {})
            uu = tj.get("interview_unit_id")
            if uu:
                ref["interview_unit_id"] = str(uu)
            if x.source_document_id:
                ref["nav"] = {
                    "kind": "document",
                    "project_id": str(x.project_id),
                    "document_id": str(x.source_document_id),
                    "chunk_id": str(x.chunk_id),
                }
            elif x.source_audio_id:
                ref["nav"] = {
                    "kind": "audio",
                    "project_id": str(x.project_id),
                    "audio_id": str(x.source_audio_id),
                    "transcript_id": str(x.transcript_id) if x.transcript_id else None,
                    "chunk_id": str(x.chunk_id),
                }
            elif x.transcript_id:
                ref["nav"] = {
                    "kind": "transcript",
                    "project_id": str(x.project_id),
                    "transcript_id": str(x.transcript_id),
                    "chunk_id": str(x.chunk_id),
                }
            else:
                ref["nav"] = {
                    "kind": "entity",
                    "project_id": str(x.project_id),
                }
            srcs.append(ref)
        out.append(
            {
                "label": title,
                "pr_signal_type": pr_sig,
                "entity_type": et,
                "count": len(elist),
                "entity_ids": [str(x.id) for x in elist],
                "source_refs": srcs,
            }
        )
    return out


def _aggregate_entities_block(entities: list[ExtractedEntity]) -> dict[str, Any]:
    topic_counts: Counter[str] = Counter()
    problem_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    pos_n = neg_n = 0
    insight_candidates: list[dict[str, Any]] = []
    statement_counts: Counter[str] = Counter()

    for e in entities:
        t = (e.title or "").strip()
        if not t or len(t) < 4:
            t = (e.content or "").strip()[:120]
        if not t or len(t) < 4:
            continue
        et = e.entity_type
        if et in _TOPIC_TYPES:
            topic_counts[t[:120]] += 1
        if et in _PROBLEM_TYPES:
            problem_counts[t[:120]] += 1
        if et in _PATTERN_TYPES:
            pattern_counts[t[:120]] += 1
        if et in _RISK_TYPES:
            risk_counts[t[:120]] += 1
        if et in _SENT_POS:
            pos_n += 1
        elif et in _SENT_NEG:
            neg_n += 1
        if et in PR_SYNTHESIS_INSIGHT_TYPES:
            pr_lab = taxonomy_label_for_entity(et, dict(e.tags_json or {}))
            quote = _entity_quote(e)
            insight_candidates.append(
                {
                    "pr_signal_type": pr_lab,
                    "entity_type": et.value,
                    "label": t[:220],
                    "text": _human_insight_text(e, t[:220], pr_lab)[:700],
                    "evidence_quote": quote,
                    "source_document_id": str(e.source_document_id) if e.source_document_id else None,
                    "source_audio_id": str(e.source_audio_id) if e.source_audio_id else None,
                    "transcript_id": str(e.transcript_id) if e.transcript_id else None,
                    "chunk_id": str(e.chunk_id),
                }
            )
        if et in (EntityType.SUPPORTING_FACT, EntityType.CLAIM, EntityType.CUSTOM, EntityType.TOPIC):
            label = (e.title or "").strip()[:120] or (e.content or "").strip()[:120]
            if len(label) >= 8:
                statement_counts[label] += 1

    if pos_n > neg_n * 1.2:
        balance = "positive"
    elif neg_n > pos_n * 1.2:
        balance = "negative"
    else:
        balance = "mixed"

    if not topic_counts and statement_counts:
        topic_counts = Counter(dict(statement_counts.most_common(12)))
    if not pattern_counts and statement_counts:
        pattern_counts = Counter(dict(statement_counts.most_common(10)))
    if not insight_candidates and entities:
        for e in entities[:40]:
            lab = ((e.title or "").strip() or (e.content or "").strip())[:400]
            if len(lab) < 12:
                continue
            pr_lab = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
            quote = _entity_quote(e)
            insight_candidates.append(
                {
                    "pr_signal_type": pr_lab,
                    "entity_type": e.entity_type.value,
                    "label": lab[:220],
                    "text": _human_insight_text(e, lab[:220], pr_lab)[:700],
                    "evidence_quote": quote,
                    "source_document_id": str(e.source_document_id) if e.source_document_id else None,
                    "source_audio_id": str(e.source_audio_id) if e.source_audio_id else None,
                    "transcript_id": str(e.transcript_id) if e.transcript_id else None,
                    "chunk_id": str(e.chunk_id),
                },
            )
            if len(insight_candidates) >= 20:
                break

    risk_taxonomy = frozenset({"risk_signal", "reputation_threat", "objection"})
    if not risk_counts:
        tax_risk: Counter[str] = Counter()
        for e in entities:
            tax = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
            if tax not in risk_taxonomy:
                continue
            lab = ((e.title or "").strip() or (e.content or "").strip())[:120]
            if len(lab) < 4:
                continue
            tax_risk[f"{tax}: {lab}"] += 1
        if tax_risk:
            risk_counts = tax_risk

    return {
        "topics_pie": [{"label": k, "value": v} for k, v in topic_counts.most_common(12)],
        "problems_bar": [{"label": k, "value": v} for k, v in problem_counts.most_common(12)],
        "risks_bar": [{"label": k, "value": v} for k, v in risk_counts.most_common(12)],
        "top_patterns": [{"text": k, "count": v} for k, v in pattern_counts.most_common(10)],
        "top_insights": insight_candidates[:20],
        "sentiment": {
            "positive_signals": pos_n,
            "negative_signals": neg_n,
            "balance": balance,
        },
    }


async def _word_frequency_for_chunk_filter(
    session: AsyncSession,
    chunk_scope: ColumnElement,
    limit: int = 40,
    *,
    apply_stopwords: bool = False,
) -> list[dict[str, Any]]:
    """``chunk_scope`` should be the return value of :func:`text_chunks_scope_and` (possibly ``false()``)."""
    ch_stmt = select(TextChunk.text).where(chunk_scope).limit(800)
    texts = list((await session.scalars(ch_stmt)).all())
    corpus = "\n".join(str(x) for x in texts if x)[:120_000]
    return [{"word": w, "count": c} for w, c in _tokenize_corpus(corpus, limit=limit, apply_stopwords=apply_stopwords)]


async def _ngrams_for_chunk_filter(
    session: AsyncSession,
    chunk_scope: ColumnElement,
    *,
    apply_stopwords: bool = False,
    limit_bi: int = 40,
    limit_tri: int = 30,
) -> dict[str, Any]:
    ch_stmt = select(TextChunk.text).where(chunk_scope).limit(800)
    texts = list((await session.scalars(ch_stmt)).all())
    corpus = "\n".join(str(x) for x in texts if x)[:120_000]
    tokens = corpus_tokens(corpus, apply_stopwords=apply_stopwords)
    return {
        "bigrams": ngram_counts(tokens, 2, limit_bi),
        "trigrams": ngram_counts(tokens, 3, limit_tri),
    }


async def _pr_lexicon_signals_for_scope(
    session: AsyncSession,
    chunk_scope: ColumnElement,
    *,
    interview_count: int,
    brand_name: str,
) -> dict[str, Any]:
    ch_stmt = (
        select(
            TextChunk.id,
            TextChunk.text,
            TextChunk.transcript_id,
            TextChunk.source_document_id,
            TextChunk.source_audio_id,
        )
        .where(chunk_scope)
        .limit(800)
    )
    rows = (await session.execute(ch_stmt)).all()
    chunks = [
        {
            "id": r[0],
            "text": r[1] or "",
            "transcript_id": r[2],
            "source_document_id": r[3],
            "source_audio_id": r[4],
        }
        for r in rows
    ]
    bt = [brand_name.strip()] if (brand_name or "").strip() else []
    return build_pr_lexicon_signals_from_chunks(
        chunks,
        interview_count=interview_count,
        brand_tokens=bt,
    )


async def _load_metadata_maps(
    session: AsyncSession,
    doc_ids: list[UUID],
    audio_ids: list[UUID],
) -> tuple[dict[UUID, dict[str, Any]], dict[UUID, dict[str, Any]], dict[UUID, UUID]]:
    doc_meta: dict[UUID, dict[str, Any]] = {}
    audio_meta: dict[UUID, dict[str, Any]] = {}
    if doc_ids:
        rows = list(
            (await session.scalars(select(SourceDocument).where(SourceDocument.id.in_(doc_ids)))).all()
        )
        for d in rows:
            doc_meta[d.id] = dict(d.metadata_json or {})
    if audio_ids:
        rows = list(
            (await session.scalars(select(SourceAudio).where(SourceAudio.id.in_(audio_ids)))).all()
        )
        for a in rows:
            audio_meta[a.id] = dict(a.metadata_json or {})
    transcript_to_audio: dict[UUID, UUID] = {}
    if audio_ids:
        stmt = select(Transcript.id, Transcript.source_audio_id).where(
            Transcript.source_audio_id.in_(audio_ids)
        )
        tr_rows = (await session.execute(stmt)).all()
        for tid, aid in tr_rows:
            transcript_to_audio[tid] = aid
    return doc_meta, audio_meta, transcript_to_audio


def _audience_snapshot_from_metas(
    metas: list[dict[str, Any]],
) -> dict[str, Any]:
    gender_c: Counter[str] = Counter()
    age_c: Counter[str] = Counter()
    seg_c: Counter[str] = Counter()
    lang_c: Counter[str] = Counter()
    city_c: Counter[str] = Counter()
    itype_c: Counter[str] = Counter()
    src_c: Counter[str] = Counter()
    date_c: Counter[str] = Counter()

    for m in metas:
        g = m.get("gender")
        if isinstance(g, list):
            for x in g:
                xs = str(x).strip()
                if xs:
                    gender_c[xs] += 1
        elif isinstance(g, str) and g.strip():
            gender_c[g.strip()] += 1

        ar = m.get("age_range")
        if isinstance(ar, dict):
            age_c[_segment_label(m, "age_range")] += 1
        elif isinstance(ar, str) and ar.strip():
            age_c[ar.strip()] += 1

        segs = m.get("segments")
        if isinstance(segs, list):
            for x in segs:
                xs = str(x).strip()
                if xs:
                    seg_c[xs] += 1

        lang = str(m.get("language") or "").strip()
        if lang:
            lang_c[lang] += 1

        city = str(m.get("city") or "").strip()
        if city:
            city_c[city] += 1

        it = str(m.get("interview_type") or "").strip()
        if it:
            itype_c[it] += 1

        src = str(m.get("source") or "").strip()
        if src:
            src_c[src] += 1

        dt = str(m.get("date") or "").strip()
        if dt:
            date_c[dt] += 1

    n = len(metas)
    return {
        "interview_count": n,
        "gender": dict(gender_c.most_common(20)),
        "age_range": dict(age_c.most_common(20)),
        "segments": dict(seg_c.most_common(30)),
        "language": dict(lang_c.most_common(20)),
        "city": dict(city_c.most_common(20)),
        "interview_type": dict(itype_c.most_common(20)),
        "source": dict(src_c.most_common(20)),
        "date": dict(date_c.most_common(20)),
    }


async def build_batch_dashboard(
    session: AsyncSession,
    batch: ResearchBatch,
    *,
    group_by: str | None = None,
    segment_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    stopwords: bool = False,
    compare_segment_a: str | None = None,
    compare_segment_b: str | None = None,
) -> dict[str, Any]:
    doc_ids = [s.source_document_id for s in batch.sources if s.source_document_id]
    audio_ids = [s.source_audio_id for s in batch.sources if s.source_audio_id]

    doc_meta, audio_meta, transcript_to_audio = (
        await _load_metadata_maps(session, doc_ids, audio_ids) if (doc_ids or audio_ids) else ({}, {}, {})
    )
    has_scope_filters = (
        (bool(segment_key) and bool(group_by) and group_by in DASHBOARD_GROUP_BY_FIELDS)
        or bool(date_from or date_to)
    )
    if doc_ids or audio_ids:
        scope_doc_ids, scope_audio_ids = narrow_source_ids(
            doc_ids,
            audio_ids,
            doc_meta,
            audio_meta,
            group_by=group_by,
            segment_key=segment_key,
            segment_label_fn=_segment_label,
            date_from=date_from,
            date_to=date_to,
            group_fields=DASHBOARD_GROUP_BY_FIELDS,
        )
    else:
        scope_doc_ids, scope_audio_ids = [], []
    if not has_scope_filters:
        scope_doc_ids, scope_audio_ids = list(doc_ids), list(audio_ids)

    transcript_ids = await resolve_transcript_ids_async(session, scope_audio_ids)

    metas: list[dict[str, Any]] = []
    for did in scope_doc_ids:
        metas.append(dict(doc_meta.get(did) or {}))
    for aid in scope_audio_ids:
        metas.append(dict(audio_meta.get(aid) or {}))

    audience_snapshot = _audience_snapshot_from_metas(metas)
    filters_echo: dict[str, Any] = {
        "group_by": group_by,
        "segment_key": segment_key,
        "date_from": date_from,
        "date_to": date_to,
        "stopwords": stopwords,
        "compare_segment_a": compare_segment_a,
        "compare_segment_b": compare_segment_b,
    }

    if not doc_ids and not audio_ids:
        wctx0: dict[str, Any] = {
            "interview_count": 0,
            "topics_pie": [],
            "problems_bar": [],
            "risks_bar": [],
            "top_patterns": [],
            "top_insights": [],
            "quotes": [],
        }
        dqr0 = assess_synthesis_readiness(wctx0, output_language="ru")
        strict0 = assess_strict_pr_readiness(
            {**wctx0, "entity_row_count": 0, "evidence_quotes_count": 0},
            output_language="ru",
        )
        return {
            "batch": {
                "id": str(batch.id),
                "name": batch.name,
                "description": batch.description,
                "project_id": str(batch.project_id),
                "source_count": 0,
                "single_file_multi_interview_mode": getattr(
                    batch, "single_file_multi_interview_mode", True
                ),
                "entity_rows_used": 0,
            },
            "topics_pie": [],
            "problems_bar": [],
            "risks_bar": [],
            "word_frequency": [],
            "sentiment": _sentiment_with_fractions(
                {"positive_signals": 0, "negative_signals": 0, "balance": "unknown"},
            ),
            "top_patterns": [],
            "top_insights": [],
            "audience_snapshot": audience_snapshot,
            "data_quality": {
                "data_coverage_score": dqr0.data_coverage_score,
                "can_synthesize_llm": dqr0.can_synthesize,
                "strict_pr_ready": strict0.ready,
                "strict_pr_message": strict0.user_message or None,
                "gates_checklist": [
                    {
                        "id": x.id,
                        "label": x.label,
                        "passed": x.passed,
                        "current": x.current,
                        "threshold": x.threshold,
                        "unit": x.unit,
                    }
                    for x in strict0.checklist
                ],
                "warnings": build_data_warnings(wctx0),
            },
            "traced": {"topics": [], "problems": [], "risks": []},
            "group_by": group_by,
            "segment_breakdown": [],
            "insight_graph": {"schema": "insight_graph_v1", "nodes": [], "edges": []},
            "interview_units": [],
            "document_pipelines": [],
            "pr_taxonomy_totals": [],
            "evidence_dashboard": {
                "kpis": {
                    "interview_count": 0,
                    "processed_interviews_estimate": 0,
                    "entity_rows": 0,
                    "evidence_quotes": 0,
                    "data_coverage_score": dqr0.data_coverage_score,
                    "extraction_quality_note": _t_quality_note(0, 0),
                    "warnings": build_data_warnings(wctx0),
                },
                "topics_problems_risks": {
                    "topics_pie": [],
                    "problems_bar": [],
                    "risks_bar": [],
                    "pr_taxonomy_bar": [],
                    "value_mode": "pct",
                },
                "sentiment": _sentiment_with_fractions(
                    {"positive_signals": 0, "negative_signals": 0, "balance": "unknown"},
                ),
                "word_phrase_tables": {
                    "words": [],
                    "bigrams": [],
                    "trigrams": [],
                    "stopword_filter": stopwords,
                },
                "segment_analytics": {"segment_breakdown": []},
                "traceability": {
                    "rows": [],
                    "label_integrity": pr_signal_tag_integrity([]),
                    "primary_signal_key": "pr_signal_type",
                    "legacy_type_key": "entity_type",
                },
                "timeline": dict(EMPTY_TIMELINE_REAL),
                "timeline_series_real": dict(EMPTY_TIMELINE_REAL),
                "pr_insight_rollups": [],
                "pr_taxonomy_totals": [],
                "risk_heatmap": {"columns": [], "rows": []},
                "sentiment_stacked_by_segment": [],
                "segment_compare": None,
                "filters": filters_echo,
                "pr_lexicon_signals": build_pr_lexicon_signals_from_chunks(
                    [],
                    interview_count=1,
                    brand_tokens=[(get_settings().research_report_brand_name or "Click").strip()],
                ),
            },
            "data_readiness_diagnostics": _build_data_readiness_diagnostics(
                interviews_total=0,
                interviews_documents_ready=0,
                transcripts_completed=0,
                chunks_total=0,
                entities_total=0,
                quotes_total=0,
                doc_rows=[],
                audio_scope_count=0,
                base_block={"topics_pie": [], "problems_bar": [], "risks_bar": []},
            ),
            "filters": filters_echo,
        }

    parts: list[Any] = []
    if scope_doc_ids:
        parts.append(ExtractedEntity.source_document_id.in_(scope_doc_ids))
    if scope_audio_ids:
        parts.append(ExtractedEntity.source_audio_id.in_(scope_audio_ids))
    if transcript_ids:
        parts.append(ExtractedEntity.transcript_id.in_(transcript_ids))

    if not parts:
        entities = []
    else:
        surface_filter = or_(*parts)
        ent_stmt = (
            select(ExtractedEntity)
            .where(
                ExtractedEntity.project_id == batch.project_id,
                ExtractedEntity.canonical_entity_id.is_(None),
                surface_filter,
            )
            .order_by(ExtractedEntity.created_at.asc())
            .limit(4000)
        )
        entities = list((await session.scalars(ent_stmt)).all())

    df_d, dt_d = parse_iso_date(date_from), parse_iso_date(date_to)
    if df_d is not None or dt_d is not None:
        entities = [
            e
            for e in entities
            if entity_matches_date_filter(
                e,
                _meta_for_entity(
                    e,
                    doc_meta=doc_meta,
                    audio_meta=audio_meta,
                    transcript_to_audio=transcript_to_audio,
                ),
                df_d,
                dt_d,
            )
        ]

    scope_tr_ids = [tid for tid, a in transcript_to_audio.items() if a in set(scope_audio_ids)]
    chunk_scope = text_chunks_scope_and(
        batch.project_id,
        document_ids=scope_doc_ids,
        audio_ids=scope_audio_ids,
        transcript_ids=scope_tr_ids,
    )
    chunks_total_cnt = await _count_chunks_for_scope(session, chunk_scope)
    wf = await _word_frequency_for_chunk_filter(session, chunk_scope, limit=60, apply_stopwords=stopwords)
    ng = await _ngrams_for_chunk_filter(session, chunk_scope, apply_stopwords=stopwords)
    brand_n = (get_settings().research_report_brand_name or "Click").strip()
    pr_lex = await _pr_lexicon_signals_for_scope(
        session,
        chunk_scope,
        interview_count=int(audience_snapshot.get("interview_count") or 1),
        brand_name=brand_n,
    )

    base_block = _aggregate_entities_block(entities)

    use_units = getattr(batch, "single_file_multi_interview_mode", True)
    uid_n = await count_units_for_documents(session, scope_doc_ids) if scope_doc_ids else 0
    if use_units and uid_n:
        audience_snapshot["interview_count"] = uid_n + len(scope_audio_ids)

    segment_breakdown: list[dict[str, Any]] = []
    if group_by == "interview_unit":
        units = await list_units_for_documents(session, scope_doc_ids, limit=2000)
        buckets: dict[str, list[ExtractedEntity]] = defaultdict(list)
        for e in entities:
            uid = str((e.tags_json or {}).get("interview_unit_id") or "").strip() or "unknown"
            buckets[uid].append(e)
        for u in units:
            key = str(u.id)
            ent_list = buckets.get(key, [])
            blk = _aggregate_entities_block(ent_list)
            segment_breakdown.append(
                {
                    "segment_key": key,
                    "entity_count": len(ent_list),
                    "unit_index": u.unit_index,
                    "language": u.language,
                    "language_confidence": u.language_confidence,
                    "split_method": u.split_method,
                    "speaker": u.speaker,
                    "topics_pie": blk["topics_pie"],
                    "problems_bar": blk["problems_bar"],
                    "risks_bar": blk["risks_bar"],
                    "word_frequency": [],
                    "sentiment": blk["sentiment"],
                    "top_patterns": blk["top_patterns"],
                    "top_insights": blk["top_insights"],
                }
            )
    elif group_by and group_by in DASHBOARD_GROUP_BY_FIELDS:
        buckets: dict[str, list[ExtractedEntity]] = defaultdict(list)
        for e in entities:
            m = _meta_for_entity(
                e, doc_meta=doc_meta, audio_meta=audio_meta, transcript_to_audio=transcript_to_audio
            )
            buckets[_segment_label(m, group_by)].append(e)

        for seg_key, ent_list in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            blk = _aggregate_entities_block(ent_list)
            # Word frequency per segment: filter chunks by sources in this segment
            doc_in_seg: set[UUID] = set()
            audio_in_seg: set[UUID] = set()
            for did in scope_doc_ids:
                if _segment_label(dict(doc_meta.get(did) or {}), group_by) == seg_key:
                    doc_in_seg.add(did)
            for aid in scope_audio_ids:
                if _segment_label(dict(audio_meta.get(aid) or {}), group_by) == seg_key:
                    audio_in_seg.add(aid)
            tr_in_seg = [tid for tid, a in transcript_to_audio.items() if a in audio_in_seg]
            seg_scope = text_chunks_scope_and(
                batch.project_id,
                document_ids=list(doc_in_seg),
                audio_ids=list(audio_in_seg),
                transcript_ids=tr_in_seg,
            )
            seg_wf = await _word_frequency_for_chunk_filter(
                session, seg_scope, limit=24, apply_stopwords=stopwords
            )
            segment_breakdown.append(
                {
                    "segment_key": seg_key,
                    "entity_count": len(ent_list),
                    "topics_pie": blk["topics_pie"],
                    "problems_bar": blk["problems_bar"],
                    "risks_bar": blk["risks_bar"],
                    "word_frequency": seg_wf,
                    "sentiment": blk["sentiment"],
                    "top_patterns": blk["top_patterns"],
                    "top_insights": blk["top_insights"],
                }
            )

    graph_ctx = {
        **base_block,
        "interview_count": int(audience_snapshot.get("interview_count") or 0),
    }
    insight_graph = build_insight_graph_v1(graph_ctx)

    topics_pct = _bar_rows_with_pct(base_block["topics_pie"])
    problems_pct = _bar_rows_with_pct(base_block["problems_bar"])
    risks_pct = _bar_rows_with_pct(base_block["risks_bar"])
    sentiment_rich = _sentiment_with_fractions(dict(base_block["sentiment"]))

    qmini: list[dict[str, Any]] = []
    for e in entities[:40]:
        t = _entity_quote(e, max_len=300)
        if len(t) < 16:
            continue
        qmini.append(
            {
                "pr_signal_type": taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {})),
                "type": e.entity_type.value,
                "text": t[:300],
                "title": (e.title or "")[:200],
                "source_document_id": str(e.source_document_id) if e.source_document_id else None,
                "source_audio_id": str(e.source_audio_id) if e.source_audio_id else None,
                "transcript_id": str(e.transcript_id) if e.transcript_id else None,
                "chunk_id": str(e.chunk_id),
            }
        )
        if len(qmini) >= 8:
            break
    wctx: dict[str, Any] = {
        "interview_count": int(audience_snapshot.get("interview_count") or 0),
        "topics_pie": base_block["topics_pie"],
        "problems_bar": base_block["problems_bar"],
        "risks_bar": base_block["risks_bar"],
        "top_patterns": base_block["top_patterns"],
        "top_insights": base_block["top_insights"],
        "quotes": qmini,
    }
    dqr = assess_synthesis_readiness(wctx, output_language="ru")
    evidence_quotes_count = 0
    for e in entities:
        ev = dict(e.evidence_json or {})
        q = str(ev.get("quote") or "").strip()
        body = (e.content or "").strip()
        if len(q) >= 8 or len(body) >= 12:
            evidence_quotes_count += 1
    strict_ctx: dict[str, Any] = {
        **wctx,
        "entity_row_count": len(entities),
        "evidence_quotes_count": evidence_quotes_count,
    }
    strict_r = assess_strict_pr_readiness(strict_ctx, output_language="ru")
    data_warnings = list(dict.fromkeys(build_data_warnings(wctx) + dqr.warnings))
    if not strict_r.ready and strict_r.user_message:
        data_warnings = list(dict.fromkeys([strict_r.user_message] + data_warnings))
    data_quality: dict[str, Any] = {
        "data_coverage_score": dqr.data_coverage_score,
        "can_synthesize_llm": dqr.can_synthesize,
        "strict_pr_ready": strict_r.ready,
        "strict_pr_message": strict_r.user_message or None,
        "gates_checklist": [
            {
                "id": x.id,
                "label": x.label,
                "passed": x.passed,
                "current": x.current,
                "threshold": x.threshold,
                "unit": x.unit,
            }
            for x in strict_r.checklist
        ],
        "warnings": data_warnings,
    }

    traced: dict[str, Any] = {
        "topics": _traced_labels(entities, _TOPIC_TYPES, limit=18),
        "problems": _traced_labels(entities, _PROBLEM_TYPES, limit=18),
        "risks": _traced_labels(entities, _RISK_TYPES, limit=16),
    }

    units_preview: list[dict[str, Any]] = []
    if doc_ids:
        for u in await list_units_for_documents(session, doc_ids, limit=120):
            units_preview.append(
                {
                    "id": str(u.id),
                    "source_document_id": str(u.source_document_id),
                    "unit_index": u.unit_index,
                    "speaker": u.speaker,
                    "language": u.language,
                    "language_confidence": u.language_confidence,
                    "split_method": u.split_method,
                    "text_preview": (u.raw_text or "")[:240],
                }
            )

    doc_rows = []
    if doc_ids:
        sdocs = list((await session.scalars(select(SourceDocument).where(SourceDocument.id.in_(doc_ids)))).all())
        for d in sdocs:
            doc_rows.append(
                {"source_document_id": str(d.id), "filename": d.filename, "pipeline": dict(d.pipeline_state_json or {})}
            )

    proc_docs = sum(
        1
        for r in doc_rows
        if isinstance((r or {}).get("pipeline"), dict)
        and _pipeline_phase((r or {}).get("pipeline") or {})
        in ("chunked", "extracted", "synthesized", "done", "parsed")
    )
    transcripts_completed = 0
    if scope_audio_ids:
        transcripts_completed = int(
            await session.scalar(
                select(func.count())
                .select_from(Transcript)
                .where(
                    Transcript.source_audio_id.in_(scope_audio_ids),
                    Transcript.status == JobStatus.COMPLETED,
                )
            )
            or 0
        )
    pr_insight_rollups = _build_pr_insight_rollups(
        entities,
        doc_meta=doc_meta,
        audio_meta=audio_meta,
        transcript_to_audio=transcript_to_audio,
    )
    pr_totals = pr_taxonomy_totals(entities)

    def _meta_e(ent: ExtractedEntity) -> dict[str, Any]:
        return _meta_for_entity(
            ent,
            doc_meta=doc_meta,
            audio_meta=audio_meta,
            transcript_to_audio=transcript_to_audio,
        )

    tl = timeline_series_real(entities, _meta_e)
    heat = risk_heatmap(
        entities,
        group_by,
        DASHBOARD_GROUP_BY_FIELDS,
        _meta_e,
        _segment_label,
    )
    stacked = sentiment_stacked_from_breakdown(segment_breakdown)
    seg_cmp = None
    if (
        compare_segment_a
        and compare_segment_b
        and group_by
        and group_by in DASHBOARD_GROUP_BY_FIELDS
        and group_by != "interview_unit"
    ):
        seg_cmp = segment_compare_pr_bars(
            entities,
            group_by,
            compare_segment_a,
            compare_segment_b,
            _meta_e,
            _segment_label,
        )

    evidence_dashboard: dict[str, Any] = {
        "kpis": {
            "interview_count": int(audience_snapshot.get("interview_count") or 0),
            "processed_interviews_estimate": 0,
            "entity_rows": len(entities),
            "evidence_quotes": evidence_quotes_count,
            "data_coverage_score": dqr.data_coverage_score,
            "extraction_quality_note": _t_quality_note(len(entities), evidence_quotes_count),
            "warnings": data_warnings[:12],
        },
        "topics_problems_risks": {
            "topics_pie": topics_pct,
            "problems_bar": problems_pct,
            "risks_bar": risks_pct,
            "pr_taxonomy_bar": pr_totals,
            "value_mode": "pct",
        },
        "sentiment": sentiment_rich,
        "word_phrase_tables": {
            "words": wf[:60],
            "bigrams": ng.get("bigrams") or [],
            "trigrams": ng.get("trigrams") or [],
            "stopword_filter": stopwords,
        },
        "segment_analytics": {
            "segment_breakdown": segment_breakdown[:24],
        },
        "traceability": {
            "rows": _traceability_rows(
                entities,
                doc_meta,
                audio_meta,
                transcript_to_audio,
                limit=80,
            ),
            "label_integrity": pr_signal_tag_integrity(entities),
            "primary_signal_key": "pr_signal_type",
            "legacy_type_key": "entity_type",
        },
        "timeline_series_real": tl,
        "timeline": tl,
        "pr_insight_rollups": pr_insight_rollups,
        "pr_taxonomy_totals": pr_totals,
        "risk_heatmap": heat,
        "sentiment_stacked_by_segment": stacked,
        "segment_compare": seg_cmp,
        "filters": filters_echo,
        "pr_lexicon_signals": pr_lex,
    }

    interviews_total_guess = int(audience_snapshot.get("interview_count") or len(batch.sources) or 0)
    processed_guess = min(interviews_total_guess, proc_docs + transcripts_completed)
    data_readiness_diagnostics = _build_data_readiness_diagnostics(
        interviews_total=interviews_total_guess,
        interviews_documents_ready=proc_docs,
        transcripts_completed=transcripts_completed,
        chunks_total=chunks_total_cnt,
        entities_total=len(entities),
        quotes_total=evidence_quotes_count,
        doc_rows=doc_rows,
        audio_scope_count=len(scope_audio_ids),
        base_block=base_block,
    )
    evidence_dashboard["kpis"]["processed_interviews_estimate"] = processed_guess

    return {
        "batch": {
            "id": str(batch.id),
            "name": batch.name,
            "description": batch.description,
            "project_id": str(batch.project_id),
            "source_count": len(batch.sources),
            "single_file_multi_interview_mode": use_units,
            "entity_rows_used": len(entities),
        },
        "topics_pie": topics_pct,
        "problems_bar": problems_pct,
        "risks_bar": risks_pct,
        "word_frequency": wf,
        "sentiment": sentiment_rich,
        "top_patterns": base_block["top_patterns"],
        "top_insights": base_block["top_insights"],
        "audience_snapshot": audience_snapshot,
        "data_quality": data_quality,
        "traced": traced,
        "group_by": group_by,
        "segment_breakdown": segment_breakdown,
        "insight_graph": insight_graph,
        "interview_units": units_preview,
        "document_pipelines": doc_rows,
        "evidence_dashboard": evidence_dashboard,
        "filters": filters_echo,
        "pr_taxonomy_totals": pr_totals,
        "data_readiness_diagnostics": data_readiness_diagnostics,
    }


async def build_project_dashboard(
    session: AsyncSession,
    project_id: UUID,
    *,
    group_by: str | None = None,
    segment_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    stopwords: bool = False,
    compare_segment_a: str | None = None,
    compare_segment_b: str | None = None,
) -> dict[str, Any]:
    """Aggregate analytics across every document/audio in the project (not limited to one batch)."""
    from types import SimpleNamespace

    proj = await session.get(Project, project_id)
    if proj is None:
        raise ValueError("project_not_found")
    doc_ids = list(
        (await session.scalars(select(SourceDocument.id).where(SourceDocument.project_id == project_id))).all()
    )
    audio_ids = list(
        (await session.scalars(select(SourceAudio.id).where(SourceAudio.project_id == project_id))).all()
    )
    sources = [SimpleNamespace(source_document_id=d, source_audio_id=None) for d in doc_ids] + [
        SimpleNamespace(source_document_id=None, source_audio_id=a) for a in audio_ids
    ]
    phantom = SimpleNamespace(
        id=project_id,
        project_id=project_id,
        name=getattr(proj, "name", "") or "Project",
        description=getattr(proj, "description", None),
        single_file_multi_interview_mode=True,
        sources=sources,
    )
    return await build_batch_dashboard(
        session,
        phantom,  # type: ignore[arg-type]
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )


def is_audio_upload(filename: str, mime_type: str | None) -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in _AUDIO_EXTS:
        return True
    m = (mime_type or "").lower()
    return m.startswith("audio/") or m.startswith("video/")  # e.g. voice memos as video/mp4
