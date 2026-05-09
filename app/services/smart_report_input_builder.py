"""Build compact synthesis input for PR research reports (smart analysis layer)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from uuid import UUID

from app.domain.enums import EntityType
from app.domain.pr_workspace import PR_SYNTHESIS_ENTITY_TYPES
from app.models.extracted_entity import ExtractedEntity
from app.utils.quote_filters import is_trivial_quote
from app.models.project import Project

# Minimal RU stopwords for frequency (not linguistic perfection — product signal).
_RU_STOP = frozenset(
    "и в во не на что за как по из к а но же ли бы мы вы он она они его ее их "
    "это этот эта эти для при без до от до над под при про со все всего также "
    "когда где кто то так там тут уже еще очень более менее просто просто "
    "есть был была были быть будет мог может нужно надо раз один два три "
    "который которая которое которые который которых".split()
)


def _norm_theme_key(s: str) -> str:
    t = s.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\sа-яё]", "", t, flags=re.IGNORECASE)
    return t[:160]


def detect_dominant_report_language(samples: list[str]) -> str:
    """Heuristic: dominant Cyrillic → ru, else en. Quotes stay untranslated in output."""
    cyr = 0
    lat = 0
    for s in samples:
        for ch in s:
            if "\u0400" <= ch <= "\u04FF":
                cyr += 1
            elif "a" <= ch <= "z" or "A" <= ch <= "Z":
                lat += 1
    if cyr == 0 and lat == 0:
        return "ru"
    if cyr >= lat * 0.45:
        return "ru"
    return "en"


def _entity_text_sample(e: ExtractedEntity) -> str:
    parts = [e.title or "", e.content or ""]
    ev = e.evidence_json if isinstance(e.evidence_json, dict) else {}
    q = ev.get("quote") if isinstance(ev.get("quote"), str) else ""
    if q:
        parts.append(q)
    return " ".join(parts)


def _collect_language_samples(entities: list[ExtractedEntity]) -> list[str]:
    out: list[str] = []
    for e in entities[:80]:
        s = _entity_text_sample(e).strip()
        if len(s) >= 12:
            out.append(s)
    return out


def _recurring_patterns(entities: list[ExtractedEntity], limit: int = 10) -> list[dict[str, Any]]:
    buckets: dict[str, list[UUID]] = {}
    for e in entities:
        if e.entity_type not in PR_SYNTHESIS_ENTITY_TYPES:
            continue
        title = (e.title or "").strip()
        if len(title) < 6:
            continue
        k = _norm_theme_key(title)
        if not k:
            continue
        buckets.setdefault(k, []).append(e.id)
    scored = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)
    out: list[dict[str, Any]] = []
    for theme_key, ids in scored[:limit]:
        uniq = list(dict.fromkeys(ids))
        out.append(
            {
                "pattern": theme_key,
                "mentions": len(uniq),
                "supporting_entity_ids": [str(u) for u in uniq[:16]],
            }
        )
    return out


def _titles_by_types(entities: list[ExtractedEntity], types: set[EntityType], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for e in entities:
        if e.entity_type not in types:
            continue
        t = (e.title or "").strip()
        if len(t) < 4 or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _key_signals(entities: list[ExtractedEntity], limit: int = 12) -> list[str]:
    """Short PR-oriented signal lines from high-signal units (no raw chunk bodies)."""
    priority_types = (
        EntityType.TRUST_ISSUE,
        EntityType.RISK,
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.ADOPTION_BARRIER,
        EntityType.USER_NEED,
        EntityType.HYPOTHESIS,
        EntityType.SENTIMENT_SIGNAL,
    )
    out: list[str] = []
    seen: set[str] = set()
    for et in priority_types:
        for e in entities:
            if e.entity_type != et:
                continue
            title = (e.title or "").strip()
            if len(title) < 8:
                continue
            line = f"[{e.entity_type.value}] {title[:220]}"
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(line)
            if len(out) >= limit:
                return out
    for e in entities:
        if e.entity_type not in PR_SYNTHESIS_ENTITY_TYPES:
            continue
        title = (e.title or "").strip()
        if len(title) < 10:
            continue
        line = f"[{e.entity_type.value}] {title[:220]}"
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


def _evidence_quotes(entities: list[ExtractedEntity], limit: int = 16) -> list[dict[str, str]]:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for e in entities:
        if e.entity_type not in PR_SYNTHESIS_ENTITY_TYPES:
            continue
        ev = e.evidence_json if isinstance(e.evidence_json, dict) else {}
        q = ev.get("quote") if isinstance(ev.get("quote"), str) else ""
        q = q.strip()
        if len(q) < 12 or is_trivial_quote(q):
            continue
        qkey = q[:200]
        if qkey in seen:
            continue
        seen.add(qkey)
        st = "interview" if e.entity_type in PR_SYNTHESIS_ENTITY_TYPES else "note"
        rows.append(
            {
                "quote": q[:280],
                "source_type": st,
                "entity_id": str(e.id),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[А-Яа-яЁёA-Za-z]{3,}", text.lower())


def _bucket_for_word(w: str) -> str | None:
    trust = (
        "довер", "надежн", "прозрачн", "безопас", "защит", "контрол", "гарант",
        "официальн", "лиценз", "регулятор",
    )
    risk = (
        "риск", "опас", "мошен", "скам", "обман", "украдут", "потеря", "тревог",
        "страх", "сомнен", "негатив", "жалоб", "кризис",
    )
    fintech = (
        "платеж", "перевод", "карт", "банк", "финанс", "деньг", "счет", "счёт",
        "кэшбэк", "кешбэк", "кредит", "займ", "брокер",
    )
    pr_comms = (
        "сми", "пресс", "коммуникац", "месседж", "нарратив", "репутац", "имидж",
        "соцсет", "телеграм", "instagram", "инстаграм", "youtube", "tiktok",
    )
    problems = (
        "проблем", "сложн", "неудобн", "баг", "ошибк", "не работает", "жалоб",
        "барьер", "боль",
    )
    lw = w.lower()
    for label, needles in (
        ("trust", trust),
        ("risk", risk),
        ("fintech", fintech),
        ("pr_comms", pr_comms),
        ("problems", problems),
    ):
        if any(n in lw for n in needles):
            return label
    return None


def build_word_frequency_analysis(corpus: str, report_language: str) -> dict[str, Any]:
    words = _tokenize_words(corpus)
    filtered = [w for w in words if w not in _RU_STOP and len(w) > 2]
    freq = Counter(filtered)
    top = dict(freq.most_common(20))
    buckets: dict[str, Counter[str]] = {
        "trust": Counter(),
        "risk": Counter(),
        "fintech": Counter(),
        "pr_comms": Counter(),
        "problems": Counter(),
    }
    for w, n in freq.items():
        b = _bucket_for_word(w)
        if b:
            buckets[b][w] += n
    trust_score = sum(buckets["trust"].values())
    risk_score = sum(buckets["risk"].values())
    total_tagged = trust_score + risk_score + 1

    if report_language == "ru":
        if risk_score > trust_score * 1.35:
            balance = "risk-dominant"
            strength = "high" if risk_score > 12 else "medium"
            interp = (
                "В лексике заметно больше маркеров тревоги и риска, чем опор на доверие — "
                "это повышает чувствительность аудитории к скептическому прочтению финтех-коммуникаций."
            )
        elif trust_score > risk_score * 1.25:
            balance = "trust-dominant"
            strength = "low"
            interp = (
                "Лексика чаще опирается на темы надёжности и прозрачности — хорошая база для спокойных "
                "регуляторно выверенных PR-формулировок."
            )
        else:
            balance = "mixed"
            strength = "medium"
            interp = (
                "Смешанный баланс доверия и риска в формулировках: важно не допустить расхождения "
                "между обещаниями в коммуникациях и тем, что люди реально обсуждают в интервью."
            )
    else:
        balance = "mixed"
        strength = "medium"
        interp = (
            "Lexical mix suggests monitoring both reassurance and risk narratives before scaling comms."
        )

    top_lex = freq.most_common(10)
    if report_language == "ru" and top_lex:
        top_join = ", ".join(w for w, _ in top_lex[:6])
        dominant_lexicon_pr_perception = (
            f"В поверхностном слое корпуса чаще встречаются слова: {top_join}. Для PR-восприятия это задаёт тон, "
            "в котором аудитория «слышит» бренд: при заметной доле тревожной лексики даже нейтральные сообщения "
            "могут читаться скептически; при спокойных опорах доверия — окно для уверенных, но выверенных формулировок."
        )
    elif top_lex:
        dominant_lexicon_pr_perception = (
            "Dominant tokens shape how the narrative sounds to outsiders; align spokespeople and owned channels "
            "with the same vocabulary the audience already uses."
        )
    else:
        dominant_lexicon_pr_perception = ""

    return {
        "word_frequency": top,
        "themed_buckets": {k: dict(v.most_common(6)) for k, v in buckets.items()},
        "pr_interpretation": interp,
        "dominant_lexicon_pr_perception": dominant_lexicon_pr_perception,
        "risk_signal_strength": strength,
        "trust_vs_risk_balance": balance,
        "tagged_token_ratio": round((trust_score + risk_score) / total_tagged, 3),
    }


def _external_research_seeds(project: Project, recurring: list[dict[str, Any]], report_language: str) -> list[str]:
    base_ru = [
        "доверие к финтех-приложениям и мобильным платежам",
        "репутация финансовых приложений коммуникации безопасность",
        "коммуникации вокруг мошенничества и защиты пользователей финтех",
        "исследования доверия аудитории к цифровым финансовым сервисам",
        "кейсы PR и репутации в финтехе",
    ]
    base_en = [
        "trust in fintech apps mobile payments",
        "financial app reputation communications safety scams",
        "audience trust research digital financial services",
        "fintech PR case studies reputation",
    ]
    seeds = list(base_ru if report_language == "ru" else base_en)
    for row in recurring[:6]:
        p = row.get("pattern")
        if isinstance(p, str) and p.strip():
            seeds.append(p.strip()[:120])
    name = (project.name or "").strip()
    if name and name not in seeds:
        seeds.insert(0, name[:120])
    out: list[str] = []
    seen: set[str] = set()
    for s in seeds:
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= 8:
            break
    return out


def _compact_snapshot_for_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep dashboard context useful but small for the final PR prompt."""
    if not isinstance(snapshot, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("totals", "entity_type_distribution", "confidence_distribution"):
        value = snapshot.get(key)
        if isinstance(value, dict):
            out[key] = value
    top = snapshot.get("top_recurring_insights")
    if isinstance(top, list):
        out["top_recurring_insights"] = top[:8]
    return out


def build_smart_report_input(
    *,
    project: Project,
    canonical_entities: list[ExtractedEntity],
    aggregation_snapshot: dict[str, Any],
    brand_name: str,
) -> dict[str, Any]:
    """Structured compact input for final PR report LLM (no raw chunk text)."""
    lang_samples = _collect_language_samples(canonical_entities)
    report_language = detect_dominant_report_language(lang_samples)

    corpus_parts: list[str] = []
    for e in canonical_entities[:120]:
        corpus_parts.append(_entity_text_sample(e))
    corpus = "\n".join(corpus_parts)
    word_block = build_word_frequency_analysis(corpus, report_language)
    recurring = _recurring_patterns(canonical_entities)

    audience_types = {EntityType.PAIN_POINT, EntityType.USER_NEED, EntityType.PROBLEM, EntityType.ADOPTION_BARRIER}
    trust_types = {EntityType.TRUST_ISSUE, EntityType.SENTIMENT_SIGNAL}
    risk_types = {EntityType.RISK, EntityType.TRUST_ISSUE}

    audience = _titles_by_types(canonical_entities, audience_types, 8)
    trust_signals = _titles_by_types(canonical_entities, trust_types, 6)
    pr_risks = _titles_by_types(canonical_entities, risk_types, 8)

    topics: list[str] = []
    seen_t: set[str] = set()
    for row in recurring:
        t = str(row.get("pattern") or "").strip()
        if t and t.lower() not in seen_t:
            seen_t.add(t.lower())
            topics.append(t)
    for e in canonical_entities:
        if e.entity_type == EntityType.TOPIC and (e.title or "").strip():
            tt = (e.title or "").strip()
            if tt.lower() not in seen_t:
                seen_t.add(tt.lower())
                topics.append(tt)
        if len(topics) >= 10:
            break

    return {
        "brand_context": {
            "company_name": brand_name,
            "domain": "fintech",
            "analysis_mode": "pr",
        },
        "report_language": report_language,
        "project_context": {
            "name": project.name,
            "description": (project.description or "")[:2000],
        },
        "key_signals": _key_signals(canonical_entities),
        "recurring_patterns": recurring,
        "audience_concerns": audience,
        "trust_signals": trust_signals,
        "pr_risks": pr_risks,
        "evidence_quotes": _evidence_quotes(canonical_entities),
        "top_topics": topics,
        "word_frequency_block": {
            "word_frequency": word_block["word_frequency"],
            "themed_buckets": word_block["themed_buckets"],
            "pr_interpretation": word_block["pr_interpretation"],
            "risk_signal_strength": word_block["risk_signal_strength"],
            "trust_vs_risk_balance": word_block["trust_vs_risk_balance"],
        },
        "external_research_seeds": _external_research_seeds(project, recurring, report_language),
        "aggregation_snapshot": _compact_snapshot_for_report(aggregation_snapshot),
    }
