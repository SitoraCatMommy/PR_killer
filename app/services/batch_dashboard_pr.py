"""PR-taxonomy-first dashboard helpers (filters, timeline, heatmap, n-grams)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.domain.enums import EntityType
from app.domain.pr_signals import (
    PR_SIGNAL_TO_ENTITY_TYPE,
    PRSignalTaxonomy,
    coerce_pr_signal,
    taxonomy_label_for_entity,
)
from app.models.extracted_entity import ExtractedEntity

_TOKEN_RE = re.compile(r"[\wа-яёА-ЯЁ]+", re.UNICODE)

# Canonical empty payload when no dated buckets (API + trend builder).
EMPTY_TIMELINE_REAL: dict[str, Any] = {
    "note": "Нет дат в metadata / created_at для построения ряда.",
    "series": [],
    "emerging": [],
    "fading": [],
}


def pr_signal_tag_integrity(entities: list[Any]) -> dict[str, Any]:
    """Detect explicit ``pr_signal`` tags that disagree with stored ``entity_type`` (mixed-label guard)."""
    mismatch = 0
    explicit = 0
    for e in entities:
        tj = dict(getattr(e, "tags_json", None) or {})
        raw = str(tj.get("pr_signal") or "").strip()
        if not raw:
            continue
        explicit += 1
        pr = coerce_pr_signal(raw)
        if pr is None:
            continue
        expected_et = PR_SIGNAL_TO_ENTITY_TYPE.get(pr)
        et = getattr(e, "entity_type", None)
        if expected_et is not None and et is not None and et != expected_et:
            mismatch += 1
    return {
        "explicit_pr_signal_tag_count": explicit,
        "entity_type_mismatch_vs_pr_signal": mismatch,
        "mixed_integrity_warning": mismatch > 0,
    }

_SENT_POS = frozenset({EntityType.SENTIMENT_SIGNAL, EntityType.TRUST_ISSUE})
_SENT_NEG = frozenset({EntityType.RISK, EntityType.PROBLEM, EntityType.PAIN_POINT})

_DASH_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "have",
        "has",
        "had",
        "was",
        "were",
        "are",
        "but",
        "not",
        "you",
        "your",
        "they",
        "their",
        "как",
        "что",
        "это",
        "все",
        "всё",
        "или",
        "для",
        "при",
        "так",
        "его",
        "её",
        "них",
        "они",
        "был",
        "была",
        "были",
        "будет",
        "ещё",
        "уже",
        "там",
        "тут",
        "когда",
        "где",
        "очень",
        "просто",
        "типа",
        "вот",
        "ну",
        "да",
        "нет",
        "меня",
        "нас",
        "вас",
        "вам",
        "мне",
        "нам",
        "про",
        "над",
        "под",
        "из",
        "по",
        "во",
        "до",
        "без",
        "она",
        "оно",
        "они",
        "мы",
        "вы",
        "он",
        "она",
        "они",
        "который",
        "которая",
        "которые",
        "которое",
        "эти",
        "этот",
        "эта",
        "тоже",
        "также",
        "более",
        "менее",
        "может",
        "можно",
        "нужно",
        "надо",
        "если",
        "то",
        "а",
        "и",
        "в",
        "на",
        "с",
        "к",
        "о",
        "у",
        "я",
        "он",
        "мы",
        "вы",
        "они",
        "бы",
        "ли",
        "же",
        "быть",
        "есть",
    }
    | frozenset(
        {
            "короче",
            "значит",
            "кстати",
            "вроде",
            "кажется",
            "наверное",
            "типу",
            "кароче",
            "блин",
            "ээ",
            "ага",
            "вобщем",
            "знаешь",
            "понимаешь",
            "слушай",
            "либо",
            "только",
            "даже",
            "хотя",
            "ибо",
            "лишь",
            "уж",
            "ведь",
            "де",
            "мол",
            "say",
            "like",
            "just",
            "really",
            "basically",
            "literally",
            "actually",
            "maybe",
            "probably",
            "kinda",
            "sorta",
            "gonna",
            "wanna",
            "gotta",
            "demak",
            "shekilli",
            "xoʻp",
            "hop",
            "mayli",
            "nimadir",
        }
    )
)


def parse_iso_date(raw: str | None) -> date | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def tokenize_corpus(
    text: str,
    limit: int = 400,
    *,
    apply_stopwords: bool = False,
) -> list[tuple[str, int]]:
    words = [w.lower() for w in _TOKEN_RE.findall(text) if len(w) > 2]
    if apply_stopwords:
        words = [w for w in words if w not in _DASH_STOPWORDS]
    return Counter(words).most_common(limit)


def ngram_counts(tokens: list[str], n: int, limit: int) -> list[dict[str, Any]]:
    if len(tokens) < n:
        return []
    c: Counter[str] = Counter()
    for i in range(len(tokens) - n + 1):
        gram = " ".join(tokens[i : i + n])
        if len(gram) >= 4:
            c[gram] += 1
    return [{"phrase": g, "count": v} for g, v in c.most_common(limit)]


def corpus_tokens(
    text: str,
    *,
    apply_stopwords: bool,
) -> list[str]:
    words = [w.lower() for w in _TOKEN_RE.findall(text) if len(w) > 2]
    if apply_stopwords:
        words = [w for w in words if w not in _DASH_STOPWORDS]
    return words


def entity_effective_date(
    e: ExtractedEntity,
    meta: dict[str, Any],
) -> date | None:
    ds = str(meta.get("date") or "").strip()[:10]
    if ds:
        d = parse_iso_date(ds)
        if d is not None:
            return d
    ca = getattr(e, "created_at", None)
    if ca is None:
        return None
    if isinstance(ca, datetime):
        return ca.astimezone(timezone.utc).date()
    return None


def entity_matches_date_filter(
    e: ExtractedEntity,
    meta: dict[str, Any],
    df: date | None,
    dt: date | None,
) -> bool:
    if df is None and dt is None:
        return True
    d = entity_effective_date(e, meta)
    if d is None:
        return True
    if df is not None and d < df:
        return False
    if dt is not None and d > dt:
        return False
    return True


def narrow_source_ids(
    doc_ids: list[UUID],
    audio_ids: list[UUID],
    doc_meta: dict[UUID, dict[str, Any]],
    audio_meta: dict[UUID, dict[str, Any]],
    *,
    group_by: str | None,
    segment_key: str | None,
    segment_label_fn: Callable[[dict[str, Any], str], str],
    date_from: str | None,
    date_to: str | None,
    group_fields: frozenset[str],
) -> tuple[list[UUID], list[UUID]]:
    df, dt = parse_iso_date(date_from), parse_iso_date(date_to)

    def meta_ok(m: dict[str, Any]) -> bool:
        if group_by and segment_key and group_by in group_fields:
            if segment_label_fn(m, group_by) != segment_key:
                return False
        if df is not None or dt is not None:
            md = parse_iso_date(str(m.get("date") or "").strip())
            if md is None:
                return True
            if df is not None and md < df:
                return False
            if dt is not None and md > dt:
                return False
        return True

    ad = [did for did in doc_ids if meta_ok(dict(doc_meta.get(did) or {}))]
    aa = [aid for aid in audio_ids if meta_ok(dict(audio_meta.get(aid) or {}))]
    return ad, aa


def pr_taxonomy_totals(entities: list[ExtractedEntity]) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for e in entities:
        lab = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        c[lab] += 1
    total = sum(c.values()) or 1
    order = [x.value for x in PRSignalTaxonomy]
    out: list[dict[str, Any]] = []
    for k in order:
        v = int(c.get(k, 0))
        if v:
            out.append({"pr_signal_type": k, "value": v, "pct": round(100.0 * v / total, 1)})
    for k, v in c.most_common():
        if k not in order and v:
            out.append({"pr_signal_type": k, "value": int(v), "pct": round(100.0 * int(v) / total, 1)})
    return out


def risk_heatmap(
    entities: list[ExtractedEntity],
    group_by: str | None,
    group_fields: frozenset[str],
    meta_for_entity: Callable[[ExtractedEntity], dict[str, Any]],
    segment_label_fn: Callable[[dict[str, Any], str], str],
) -> dict[str, Any]:
    if not group_by or group_by not in group_fields or group_by == "interview_unit":
        return {"columns": [], "rows": []}
    risk_types = frozenset({"risk_signal", "reputation_threat", "objection"})
    mat: dict[tuple[str, str], int] = defaultdict(int)
    segs: set[str] = set()
    for e in entities:
        pr = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        if pr not in risk_types:
            continue
        m = meta_for_entity(e)
        seg = segment_label_fn(m, group_by)
        segs.add(seg)
        mat[(seg, pr)] += 1
    cols = sorted(risk_types)
    row_segs = sorted(segs)[:24]
    rows = [
        {
            "segment": seg,
            "cells": [{"pr_signal_type": col, "count": int(mat[(seg, col)])} for col in cols],
        }
        for seg in row_segs
    ]
    return {"columns": [{"pr_signal_type": c} for c in cols], "rows": rows}


def sentiment_stacked_from_breakdown(segment_breakdown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in segment_breakdown:
        s = row.get("sentiment") or {}
        pos = int(s.get("positive_signals") or 0)
        neg = int(s.get("negative_signals") or 0)
        tot = pos + neg or 1
        out.append(
            {
                "segment": row.get("segment_key"),
                "positive": pos,
                "negative": neg,
                "positive_pct": round(100.0 * pos / tot, 1),
                "negative_pct": round(100.0 * neg / tot, 1),
                "balance": s.get("balance"),
            }
        )
    return out


def segment_compare_pr_bars(
    entities: list[ExtractedEntity],
    group_by: str,
    seg_a: str,
    seg_b: str,
    meta_for_entity: Callable[[ExtractedEntity], dict[str, Any]],
    segment_label_fn: Callable[[dict[str, Any], str], str],
) -> dict[str, Any]:
    def bucket(seg: str) -> list[ExtractedEntity]:
        return [
            e
            for e in entities
            if segment_label_fn(meta_for_entity(e), group_by) == seg
        ]

    return {
        "group_by": group_by,
        "segment_a": seg_a,
        "segment_b": seg_b,
        "pr_taxonomy_a": pr_taxonomy_totals(bucket(seg_a)),
        "pr_taxonomy_b": pr_taxonomy_totals(bucket(seg_b)),
    }


def timeline_series_real(
    entities: list[ExtractedEntity],
    meta_for_entity: Callable[[ExtractedEntity], dict[str, Any]],
) -> dict[str, Any]:
    def week_key(d: date) -> str:
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"

    buckets: dict[str, dict[str, Any]] = {}
    for e in entities:
        m = meta_for_entity(e)
        d = entity_effective_date(e, m)
        if d is None:
            continue
        k = week_key(d)
        if k not in buckets:
            buckets[k] = {
                "period": k,
                "positive": 0,
                "negative": 0,
                "risk_hits": 0,
                "theme_hits": 0,
                "label_counts": Counter(),
            }
        pr = taxonomy_label_for_entity(e.entity_type, dict(e.tags_json or {}))
        title = ((e.title or "").strip()[:80] or (e.content or "").strip()[:40]).strip()
        if e.entity_type in _SENT_POS:
            buckets[k]["positive"] += 1
        elif e.entity_type in _SENT_NEG:
            buckets[k]["negative"] += 1
        if pr in ("risk_signal", "reputation_threat"):
            buckets[k]["risk_hits"] += 1
        if pr in ("message_resonance", "proof_point", "trust_driver"):
            buckets[k]["theme_hits"] += 1
        if title:
            buckets[k]["label_counts"][title] += 1

    if not buckets:
        return dict(EMPTY_TIMELINE_REAL)

    keys_sorted = sorted(buckets.keys())
    max_risk = max((int(buckets[k]["risk_hits"]) for k in keys_sorted), default=0) or 1
    series: list[dict[str, Any]] = []
    for k in keys_sorted:
        b = buckets[k]
        pos, neg = int(b["positive"]), int(b["negative"])
        bal = pos - neg
        tot = pos + neg or 1
        rv = int(b["risk_hits"])
        sentiment_score = int(max(0, min(100, round(50.0 + 50.0 * bal / tot))))
        risk_index = int(max(0, min(100, round(100.0 * rv / max_risk))))
        series.append(
            {
                "period": k,
                "sentiment_balance": bal,
                "positive_signals": pos,
                "negative_signals": neg,
                "risk_volume": rv,
                "theme_volume": int(b["theme_hits"]),
                "sentiment_score": sentiment_score,
                "risk_index": risk_index,
            }
        )

    n = len(keys_sorted)
    emerging: list[str] = []
    fading: list[str] = []
    if n >= 2:
        i1 = max(1, n // 3)
        i2 = max(1, (2 * n) // 3)
        early: Counter[str] = Counter()
        late: Counter[str] = Counter()
        for kk in keys_sorted[:i1]:
            early.update(buckets[kk]["label_counts"])
        for kk in keys_sorted[i2:]:
            late.update(buckets[kk]["label_counts"])
        emerging = [t for t, _ in (late - early).most_common(4)]
        fading = [t for t, _ in (early - late).most_common(4)]

    return {
        "note": "Недельные корзины по дате из metadata (date) или по дате создания сущности.",
        "series": series,
        "emerging": emerging,
        "fading": fading,
    }
