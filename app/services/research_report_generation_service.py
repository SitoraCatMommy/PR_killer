"""Build `ResearchReport` from canonical units + aggregation + external research (OpenAI JSON)."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import EntityType, ReportStatus
from app.domain.pr_workspace import PR_SYNTHESIS_ENTITY_TYPES
from app.domain.research_constants import PERIOD_KEY_ALL_TIME, SNAPSHOT_TYPE_RESEARCH_ENTITIES
from app.domain.research_units import PRIMARY_RESEARCH_ENTITY_TYPES
from app.infrastructure.settings import Settings, get_settings
from app.models.aggregation_snapshot import AggregationSnapshot
from app.models.extracted_entity import ExtractedEntity
from app.models.project import Project
from app.models.research_report import ResearchReport
from app.services.external_research.factory import get_external_research_provider
from app.services.smart_report_input_builder import build_smart_report_input
from app.utils.quote_filters import is_trivial_quote

logger = logging.getLogger(__name__)

_MAX_CANONICAL_LOAD = 300
_MAX_UNITS_IN_PROMPT = 60
_MAX_UNIT_CHARS = 420
_MAX_QUOTE_CHARS = 320
_MAX_SNAPSHOT_JSON_CHARS = 14_000
_DEFAULT_MAX_USER_JSON_CHARS = 45_000

# Sections whose items should carry analytical sub-fields + display "text" for API/UI.
_ANALYTICAL_SECTION_KEYS = (
    "key_findings",
    "problems",
    "patterns",
    "risks",
    "hypotheses",
    "recommendations",
    "forecast",
)

# Продуктовые / UX / growth-формулировки — в отчёте запрещены; постобработка переписывает или ослабляет.
_PRODUCT_ADVICE_RE = re.compile(
    r"(?:улучшить\s*(?:ux|опыт|интерфейс|продукт|сервис|приложен(?:ие|ия)|клиентск(?:ий|ое|ую)?)|"
    r"интегрир(?:овать|ация|оваться)|добавить\s+(?:в\s+)?(?:приложен(?:ие|ия)|продукт|сервис|функц)|"
    r"новостн\w*\s*лент|лента\s+новост|"
    r"повысить\s+вовлеч\w*|рост\s+вовлеч\w*|adoption|onboarding|retention|\bux\b|\bui\b|\bfeature\b|\bmvp\b|road\s?map|"
    r"экран\s+(?:подтвержд|оплат)|функционал|фич[аи]?\b|"
    r"продуктов(?:ое|ая|ые|ых)\s+(?:изменение|решение|улучшение|доработк)|"
    r"customer\s*journey|user\s*journey|юзер\s*флоу|"
    r"внедрить\s+(?:в\s+)?(?:приложен|продукт)|расширить\s+функционал|"
    r"добавить\s+функц|расширить\s+партнёр|оптимизировать\s+приложен|улучшить\s+производительност|"
    r"улучшить\s+качество\s+приложен|ускорить\s+работу\s+приложен|новая\s+функц)",
    re.IGNORECASE | re.UNICODE,
)

# Строковые поля пунктов, где ищем продуктовый язык для PR-фильтра.
_PR_ITEM_STRING_KEYS = (
    "finding",
    "explanation",
    "causal_chain",
    "impact",
    "recommendation",
    "forecast",
    "text",
    "comms_signal",
    "pr_relevance",
    "reputation_gap",
    "pr_action",
    "comms_follow_up",
    "insight_fact",
    "pr_risk_why",
    "message_what_to_say",
    "channel_where",
    "tone_format_how",
)

# Латиница в пользовательских инсайтах отчёта не допускается (кроме URL/UUID — отфильтруем грубо).
_FORBIDDEN_ENGLISH_IN_OUTPUT_RE = re.compile(
    r"\b(performance|integration|improve|improving|optimize|optimizing|feature|features|quality|"
    r"user\s*experience|roadmap|release|deployment|backend|frontend|dashboard)\b",
    re.IGNORECASE,
)

_RECOMMENDATION_FIVE_KEYS = (
    "insight_fact",
    "pr_risk_why",
    "message_what_to_say",
    "channel_where",
    "tone_format_how",
)


def _as_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v]
    return []


def _merge_theme_lists(primary: list[str], secondary: list[str], max_n: int = 14) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for src in (primary, secondary):
        for x in src:
            t = (x or "").strip()
            if not t:
                continue
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(t[:200])
            if len(out) >= max_n:
                return out
    return out


def _canonical_entity_index(entities: list[ExtractedEntity], limit: int = 180) -> list[dict[str, Any]]:
    return [
        {"id": str(e.id), "type": e.entity_type.value, "title": (e.title or "")[:240]}
        for e in entities[:limit]
    ]


def _normalize_talking_points(raw: Any, max_items: int = 14) -> list[str]:
    out: list[str] = []
    for it in _as_list(raw):
        if not isinstance(it, str):
            continue
        s = it.strip()
        if not s:
            continue
        words = s.split()
        if len(words) > 20:
            s = " ".join(words[:20]).rstrip(",;:")
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_short_string_list(raw: Any, max_items: int = 16) -> list[str]:
    out: list[str] = []
    for it in _as_list(raw):
        if isinstance(it, str) and it.strip():
            out.append(it.strip()[:500])
        if len(out) >= max_items:
            break
    return out


def _normalize_pr_bullet_list(raw: Any, max_items: int = 14) -> list[str]:
    out: list[str] = []
    for it in _as_list(raw):
        if isinstance(it, str) and it.strip():
            out.append(it.strip()[:800])
        elif isinstance(it, dict):
            s = str(it.get("text") or it.get("statement") or it.get("risk") or "").strip()
            if s:
                out.append(s[:800])
        if len(out) >= max_items:
            break
    return out


def _merge_word_analysis(builder_block: dict[str, Any] | None, llm_block: Any) -> dict[str, Any]:
    b = dict(builder_block or {})
    out: dict[str, Any] = {
        "word_frequency": b.get("word_frequency") if isinstance(b.get("word_frequency"), dict) else {},
        "themed_buckets": b.get("themed_buckets") if isinstance(b.get("themed_buckets"), dict) else {},
        "pr_interpretation": str(b.get("pr_interpretation") or "").strip(),
        "dominant_lexicon_pr_perception": str(b.get("dominant_lexicon_pr_perception") or "").strip(),
        "risk_signal_strength": b.get("risk_signal_strength") or "medium",
        "trust_vs_risk_balance": b.get("trust_vs_risk_balance") or "mixed",
    }
    if not isinstance(llm_block, dict):
        return out
    for k in ("pr_interpretation", "dominant_lexicon_pr_perception", "risk_signal_strength", "trust_vs_risk_balance"):
        v = llm_block.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    wf = llm_block.get("word_frequency")
    if isinstance(wf, dict) and wf:
        out["word_frequency"] = wf
    tb = llm_block.get("themed_buckets")
    if isinstance(tb, dict) and tb:
        out["themed_buckets"] = tb
    return out


def _normalize_external_article_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    if not title or not url:
        return {}
    summary = str(row.get("summary") or "").strip()
    why = str(row.get("why_relevant_for_pr") or row.get("relevance") or "").strip()
    return {"title": title, "url": url, "summary": summary, "why_relevant_for_pr": why}


def _normalize_external_articles_list(raw: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = _as_list(raw)
    merged: list[dict[str, Any]] = []
    for it in items:
        n = _normalize_external_article_row(it)
        if n:
            merged.append(n)
    if merged:
        return merged
    out_fb: list[dict[str, Any]] = []
    for it in fallback:
        n = _normalize_external_article_row(it)
        if n:
            out_fb.append(n)
    return out_fb


def _brief_entity(e: ExtractedEntity) -> dict[str, Any]:
    ev = e.evidence_json if isinstance(e.evidence_json, dict) else {}
    q = ev.get("quote") if isinstance(ev.get("quote"), str) else ""
    return {
        "id": str(e.id),
        "type": e.entity_type.value,
        "title": (e.title or "").strip(),
        "content": (e.content or "")[:_MAX_UNIT_CHARS],
        "quote": q[:_MAX_QUOTE_CHARS],
        "confidence": e.confidence_score,
    }


def _norm_theme_key(s: str) -> str:
    t = s.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\sа-яё]", "", t, flags=re.IGNORECASE)
    return t[:160]


def _recurring_themes(entities: list[ExtractedEntity], limit: int = 14) -> list[dict[str, Any]]:
    """Surface repeated titles across canonical units (synthesis hints, not raw chunks)."""
    buckets: dict[str, list[UUID]] = {}
    for e in entities:
        if e.entity_type not in PRIMARY_RESEARCH_ENTITY_TYPES:
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
                "theme": theme_key,
                "signal_count": len(uniq),
                "unit_ids": [str(u) for u in uniq[:12]],
            }
        )
    return out


def _quotes_from_entities(entities: list[ExtractedEntity], limit: int = 40) -> list[dict[str, str]]:
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
        rows.append({"entity_id": str(e.id), "quote": q[:_MAX_QUOTE_CHARS]})
        if len(rows) >= limit:
            break
    return rows


def _entity_sort_key(e: ExtractedEntity) -> tuple[int, float, str]:
    primary = 0 if e.entity_type in PR_SYNTHESIS_ENTITY_TYPES else 1
    conf = e.confidence_score
    c = 0.0 if conf is None or conf != conf else float(conf)
    return (primary, -c, (e.title or "")[:200])


def _select_prompt_entities(canonicals: list[ExtractedEntity]) -> list[ExtractedEntity]:
    ordered = sorted(canonicals, key=_entity_sort_key)
    return ordered[:_MAX_UNITS_IN_PROMPT]


def _select_synthesis_entities(canonicals: list[ExtractedEntity]) -> list[ExtractedEntity]:
    pr_entities = [e for e in canonicals if e.entity_type in PR_SYNTHESIS_ENTITY_TYPES]
    if pr_entities:
        return pr_entities
    return [e for e in canonicals if e.entity_type != EntityType.SUPPORTING_FACT][:40]


def _group_by_type(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        t = str(r.get("type") or "unknown")
        grouped.setdefault(t, []).append(r)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0]))


def _type_counts(entities: list[ExtractedEntity]) -> dict[str, int]:
    c = Counter(e.entity_type.value for e in entities)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def _trim_json_value(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) <= max_chars:
        return payload
    return {
        "_truncated": True,
        "aggregation_keys": list(payload.keys())[:40],
        "aggregation_excerpt": raw[:max_chars],
    }


def _compact_aggregation_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for key in ("totals", "entity_type_distribution", "confidence_distribution"):
        value = payload.get(key)
        if isinstance(value, dict):
            out[key] = value
    top = payload.get("top_recurring_insights")
    if isinstance(top, list):
        out["top_recurring_insights"] = top[:8]
    return out


def _bounded_user_payload_json(payload: dict[str, Any], *, max_chars: int) -> str:
    """Deterministically trim lower-priority report input before final safety truncation."""
    working = dict(payload)
    raw = json.dumps(working, ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw

    synthesis = working.get("synthesis_input")
    if isinstance(synthesis, dict):
        synthesis = dict(synthesis)
        working["synthesis_input"] = synthesis
        if isinstance(synthesis.get("aggregation_snapshot"), dict):
            synthesis["aggregation_snapshot"] = _compact_aggregation_snapshot(
                synthesis["aggregation_snapshot"]
            )
        for key, keep in (
            ("evidence_quotes", 10),
            ("key_signals", 10),
            ("recurring_patterns", 8),
            ("top_topics", 8),
            ("external_research_seeds", 6),
        ):
            value = synthesis.get(key)
            if isinstance(value, list):
                synthesis[key] = value[:keep]
        wf = synthesis.get("word_frequency_block")
        if isinstance(wf, dict):
            wf = dict(wf)
            synthesis["word_frequency_block"] = wf
            freq = wf.get("word_frequency")
            if isinstance(freq, dict):
                wf["word_frequency"] = dict(list(freq.items())[:20])
            buckets = wf.get("themed_buckets")
            if isinstance(buckets, dict):
                wf["themed_buckets"] = {
                    str(k): dict(list(v.items())[:6]) if isinstance(v, dict) else v
                    for k, v in buckets.items()
                }

    entity_index = working.get("canonical_entity_index")
    if isinstance(entity_index, list):
        working["canonical_entity_index"] = entity_index[:40]
    draft_external = working.get("draft_external_articles")
    if isinstance(draft_external, list):
        working["draft_external_articles"] = draft_external[:6]

    raw = json.dumps(working, ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1] + "…"


def _load_snapshot(session: Session, project_id: UUID) -> dict[str, Any]:
    row = session.scalar(
        select(AggregationSnapshot)
        .where(
            AggregationSnapshot.project_id == project_id,
            AggregationSnapshot.snapshot_type == SNAPSHOT_TYPE_RESEARCH_ENTITIES,
            AggregationSnapshot.period_key == PERIOD_KEY_ALL_TIME,
        )
        .order_by(AggregationSnapshot.created_at.desc())
        .limit(1)
    )
    if row is None:
        return {}
    return dict(row.payload_json or {})


def _infer_search_themes(entities: list[ExtractedEntity]) -> list[str]:
    seen: list[str] = []
    priority = {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.TRUST_ISSUE,
        EntityType.ADOPTION_BARRIER,
        EntityType.RISK,
        EntityType.HYPOTHESIS,
    }
    for e in entities:
        if e.entity_type in priority and e.title:
            t = e.title.strip()
            if t and t not in seen:
                seen.append(t)
        if len(seen) >= 8:
            break
    for e in entities:
        if e.entity_type in PRIMARY_RESEARCH_ENTITY_TYPES and e.title:
            t = e.title.strip()
            if t and t not in seen:
                seen.append(t)
        if len(seen) >= 10:
            break
    return seen or ["Пользовательское исследование"]


def _strip_urls_and_uuid_tokens(s: str) -> str:
    s = re.sub(r"https?://\S+", " ", s, flags=re.IGNORECASE)
    return re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        " ",
        s,
        flags=re.IGNORECASE,
    )


def _collect_strings_for_pr_validation(data: dict[str, Any]) -> str:
    """Тексты ответа модели для проверки (цитаты интервью из quote не штрафуем за латиницу в URL)."""
    chunks: list[str] = []
    for k in ("title", "description", "executive_summary"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            chunks.append(v)
    for sec in _ANALYTICAL_SECTION_KEYS:
        for item in _as_list(data.get(sec)):
            if isinstance(item, dict):
                for kk, vv in item.items():
                    if isinstance(vv, str) and vv.strip():
                        chunks.append(vv)
            elif isinstance(item, str) and item.strip():
                chunks.append(item)
    for it in _as_list(data.get("next_steps")):
        if isinstance(it, dict):
            for kk, vv in it.items():
                if isinstance(vv, str) and vv.strip():
                    chunks.append(vv)
        elif isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("supporting_quotes")):
        if isinstance(it, dict):
            n = it.get("note")
            if isinstance(n, str) and n.strip():
                chunks.append(n)
    for it in _as_list(data.get("talking_points")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("infopovody")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("open_questions")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("reputational_risks")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("communication_gaps")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    for it in _as_list(data.get("next_steps_pr")):
        if isinstance(it, str) and it.strip():
            chunks.append(it)
    wa = data.get("word_analysis")
    if isinstance(wa, dict):
        for kk in ("pr_interpretation", "dominant_lexicon_pr_perception"):
            vv = wa.get(kk)
            if isinstance(vv, str) and vv.strip():
                chunks.append(vv)
    for it in _as_list(data.get("external_articles")):
        if isinstance(it, dict):
            for kk in ("relevance", "summary", "why_relevant_for_pr"):
                vv = it.get(kk)
                if isinstance(vv, str) and vv.strip():
                    chunks.append(vv)
    return "\n".join(chunks)


def _report_data_validation_errors(data: dict[str, Any], *, report_language: str) -> list[str]:
    """Compact validation errors used for cheap repair prompts."""
    errors: list[str] = []
    blob = _collect_strings_for_pr_validation(data)
    if _PRODUCT_ADVICE_RE.search(blob):
        errors.append("product_or_ux_language_present")
    if report_language == "ru":
        scrubbed = _strip_urls_and_uuid_tokens(blob)
        if _FORBIDDEN_ENGLISH_IN_OUTPUT_RE.search(scrubbed):
            errors.append("english_terms_present_in_russian_report")
    recs = _as_list(data.get("recommendations"))
    if recs:
        for item in recs:
            if not isinstance(item, dict):
                errors.append("recommendation_item_is_not_object")
                break
            for fk in _RECOMMENDATION_FIVE_KEYS:
                if len(str(item.get(fk, "") or "").strip()) < 10:
                    errors.append(f"recommendation_missing_{fk}")
                    break
    if report_language == "ru":
        es = str(data.get("executive_summary") or "").strip()
        if len(es) < 40 and _as_list(data.get("key_findings")):
            errors.append("executive_summary_too_short")
        for tp in _normalize_talking_points(data.get("talking_points")):
            if len(tp.split()) > 22:
                errors.append("talking_point_too_long")
                break
        if _as_list(data.get("key_findings")):
            if len(_normalize_talking_points(data.get("talking_points"))) < 2:
                errors.append("not_enough_talking_points")
            if not _normalize_pr_bullet_list(data.get("reputational_risks")):
                errors.append("missing_reputational_risks")
            if not _normalize_pr_bullet_list(data.get("communication_gaps")):
                errors.append("missing_communication_gaps")
            if not _normalize_pr_bullet_list(data.get("next_steps_pr")):
                errors.append("missing_next_steps_pr")
    return list(dict.fromkeys(errors))


def _report_data_fails_pr_validation(data: dict[str, Any], *, report_language: str) -> bool:
    """True — нужна перегенерация: продукт/UX-язык, английский в инсайтах или неверный формат рекомендаций."""
    return bool(_report_data_validation_errors(data, report_language=report_language))


def _regeneration_user_hint(
    brand_name: str,
    report_language: str,
    validation_errors: list[str] | None = None,
) -> str:
    lang_tail = (
        "Все инсайты и выводы — только на русском, без английских слов в тексте (ключи JSON можно латиницей)."
        if report_language == "ru"
        else "All narrative fields (title, description, executive_summary, sections, talking_points, etc.) in English; "
        "no Russian in analytical text. JSON keys stay ASCII."
    )
    return (
        "ВАЛИДАЦИЯ НЕ ПРОЙДЕНА. Перегенерируй весь JSON целиком.\n"
        f"Ошибки проверки: {', '.join(validation_errors or ['unknown'])}.\n"
        f"Контекст: финтех, бренд «{brand_name}». НИКОГДА не подменяй и не выдумывай название бренда; при сомнении пиши «приложение {brand_name}».\n"
        "Запрещено: любые продуктовые и UX-решения (функции, экраны, оптимизация приложения, вовлечённость, партнёрская сеть продукта и т.д.).\n"
        "Только PR: восприятие, доверие, коммуникация, репутация, барьеры восприятия.\n"
        "Каждый объект в recommendations ОБЯЗАН содержать непустые строки (от 10 символов) в полях: "
        "insight_fact, pr_risk_why, message_what_to_say, channel_where, tone_format_how.\n"
        "Должны быть заполнены: talking_points (≥2 строки), reputational_risks, communication_gaps, next_steps_pr (конкретные шаги PR с глаголом), "
        "infopovody, open_questions и объект word_analysis (в т.ч. dominant_lexicon_pr_perception при наличии данных).\n"
        f"{lang_tail}"
    )


def _build_report_system(brand_name: str, report_language: str) -> str:
    b = (brand_name or "Click").strip() or "Click"
    lang_rule = (
        "Весь смысловой текст (кроме дословных цитат из входа) строго на русском; без английских слов и фраз в инсайтах."
        if report_language == "ru"
        else "Write all analytical narrative in English (keys remain ASCII). Quotes from sources stay in their original language."
    )
    tp_rule = (
        "talking_points: массив 8–14 коротких строк; каждая — один месседж, до 12–20 слов, без рекламного тона, пригодно для PR-коммуникации."
        if report_language == "ru"
        else "talking_points: 8–14 short strings; one punchy message per line (~12–18 words), neutral PR tone, no hype."
    )
    return f"""Ты — ведущий PR- и коммуникационный аналитик (финтех). Работаешь с интервью как с PR intelligence: восприятие, доверие, коммуникация, репутация, барьеры восприятия. Ты НЕ продакт-менеджер и НЕ UX-консультант.

РЕЖИМ: smart synthesis — опирайся на synthesis_input (сжатый аналитический слой), canonical_entity_index (только id/тип/заголовок для grounded_in) и draft_external_articles. Не пересказывай интервью; синтезируй сигналы. Не выдумывай факты, цифры, названия продуктов и ссылки: всё содержательное — из synthesis_input / цитат / агрегатов; если данных мало — честно сузь выводы.

КРИТИЧЕСКИЙ КОНТЕКСТ КОМПАНИИ
- Компания / бренд: {b} (финтех).
- СТРОГО: никогда не подменяй и не выдумывай название бренда; не используй другие торговые имена.
- Если в данных нет явного названия — формулируй «приложение {b}» или «сервис {b}».

ТИП АНАЛИЗА — ТОЛЬКО PR
Запрещённые формулировки и идеи (недопустимы ни в одном поле):
- «добавить функционал», «улучшить UX», «расширить партнёрскую сеть» (в продуктовом смысле), «оптимизировать приложение»,
- любые изменения продукта, интерфейса, фич, экранов, производительности как «решение».
Анализируй: восприятие, доверие, коммуникацию, репутацию, барьеры восприятия и нарратив.

ЯЗЫК ОТЧЁТА (report_language в user JSON = {report_language})
- {lang_rule}
- Цитаты (supporting_quotes.quote) — только дословно из evidence, без перевода.

ЛОГИКА КАЖДОГО ВЫВОДА (мысленно и в тексте)
Факт (что происходит в голове аудитории / в повестке) → что это значит для восприятия бренда {b} → какой репутационный или коммуникационный риск → что делать в коммуникациях (не в продукте).

ПРИМЕР ЗАМЕНЫ СМЫСЛА
Неверно: «Нужно добавить функцию контроля расходов».
Верно: «Аудитория ощущает потерю контроля над расходами; это бьёт по доверию к {b} как к инструменту управления деньгами. В коммуникациях сместить акцент на ощущение контроля и прозрачности: объяснять, как сервис помогает видеть операции и статусы, без предложений новых продуктовых фич.»

СЕМАНТИКА СЕКЦИЙ (имена ключей JSON не менять)
- key_findings — ключевые PR-выводы (восприятие бренда, доверие).
- problems — тревоги и ожидания аудитории.
- patterns — коммуникационные сигналы (где и как формируется повестка).
- risks — репутационные и коммуникационные риски.
- hypotheses — PR-гипотезы (что может усилиться в медиаполе).
- forecast — прогноз нарратива / внимания к бренду при текущей коммуникации.
- recommendations — только PR-рекомендации (не продукт).

СТРУКТУРА ОБЪЕКТОВ (key_findings, problems, patterns, risks, hypotheses, forecast) — как раньше:
comms_signal, pr_relevance, reputation_gap, pr_action, comms_follow_up, finding, explanation, causal_chain (сигнал в интервью → восприятие/доверие → риск для репутации), impact (для бренда и доверия), recommendation (только PR-действия: Q&A, месседжи, каналы, тест формулировок, спикер, опережающий ответ, мониторинг, антикризис, площадки), forecast (репутационный, если не коммуницировать), grounded_in, text (связный абзац 6–10 предложений).

РАЗДЕЛ recommendations — СТРОГИЙ ФОРМАТ
Каждый элемент массива recommendations ОБЯЗАН содержать все поля ({'строки на русском, не короче 10 символов каждая' if report_language == 'ru' else 'strings in English, each at least 10 characters'}):
1) insight_fact — что происходит (инсайт для PR);
2) pr_risk_why — почему это риск именно для PR / репутации;
3) message_what_to_say — что говорить (ядро месседжа);
4) channel_where — где говорить (каналы и форматы; конкретизируй, если следует из интервью);
5) tone_format_how — как говорить (тон и формат).
Плюс остальные поля блока (comms_signal … recommendation …) и grounded_in, text.

Резюме executive_summary: 5–6 предложений — доверие и восприятие {b}, не про фичи.
Next_steps: только PR-действия; каждый пункт — конкретный глагол в начале (подготовить, согласовать, проверить, сформулировать…), выполним PR-командой; не «улучшить опыт» и не «добавить функцию».

{tp_rule}

infopovody: массив 4–8 коротких тем/инфоповодов для PR (если данных мало — меньше).

open_questions: 3–8 вопросов, которые PR-команде стоит доисследовать или зафиксировать в Q&A.

word_analysis: объект; уточни pr_interpretation, dominant_lexicon_pr_perception (что доминирующие слова значат для PR-восприятия и нарратива), risk_signal_strength, trust_vs_risk_balance — на основе synthesis_input.word_frequency_block (не выдумывай слова вне корпуса).

reputational_risks: массив 5–10 строк — только репутационные и коммуникационные риски для бренда (не баги продукта); каждая строка конкретна.

communication_gaps: массив 4–8 строк — зазоры между тем, что аудитория понимает/чувствует, и тем, как бренд коммуницирует.

next_steps_pr: массив 6–12 строк — только PR-действия; каждая начинается с глагола (Подготовить, Согласовать, Проверить…); без «улучшить UX» и «добавить функцию».

supporting_quotes: из synthesis_input.evidence_quotes; в note — зачем цитата для PR-вывода; quote — дословно.
external_articles: только черновики из draft_external_articles (URL); summary и why_relevant_for_pr — через призму PR и репутации (на языке отчёта).

Верни один JSON-объект с ключами:
title, description, executive_summary,
key_findings, problems, patterns, risks, hypotheses, recommendations, forecast, next_steps,
talking_points, reputational_risks, communication_gaps, next_steps_pr,
infopovody, open_questions, word_analysis,
supporting_quotes, external_articles."""


def _item_blob(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in _PR_ITEM_STRING_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return "\n".join(parts).lower()


def _item_has_product_advice(item: dict[str, Any]) -> bool:
    return bool(_PRODUCT_ADVICE_RE.search(_item_blob(item)))


def _pr_template_bundle(context: str) -> tuple[str, str, str]:
    """Три связанные PR-формулировки: основная рекомендация, действие команды, follow-up."""
    ctx = context.lower()
    if any(
        x in ctx
        for x in (
            "мошенник",
            "мошеннич",
            "обман",
            "безопасност",
            "довер",
            "страх",
            "тревог",
            "риск",
            "украдут",
            "скам",
        )
    ):
        return (
            "Подготовить расширенный Q&A и тезисы о безопасности, прозрачности процессов и контроле рисков; "
            "согласовать единую линию для спикеров, СМИ и официальных соцканалов; протестировать формулировки на понятность и снятие тревоги.",
            "Усилить опорные месседжи доверия: фактура, подтверждения, экспертные и партнёрские комментарии; избегать общих обещаний без опоры на проверяемые формулировки.",
            "Включить мониторинг обсуждений темы в СМИ и соцсетях; определить триггеры для опережающего ответа и держать готовый пакет уточнений.",
        )
    if any(
        x in ctx
        for x in (
            "сми",
            "онлайн",
            "телеграм",
            "telegram",
            "инстаграм",
            "tiktok",
            "соцсет",
            "youtube",
            "канал",
            "площадк",
            "мессендж",
        )
    ):
        return (
            "Зафиксировать, каким каналам и форматам аудитория доверяет в теме; скорректировать медиаплан и приоритет площадок "
            "(в т.ч. мессенджеры и соцсети, если это следует из интервью).",
            "Подготовить адаптированные месседжи и форматы под выбранные каналы; разработать Q&A для комментаторов и спикеров.",
            "Настроить отслеживание нарратива по ключевым площадкам; при искажениях — готовить точечный официальный ответ и бриф для ЛПР.",
        )
    if any(x in ctx for x in ("кризис", "негатив", "скандал", "атак", "обвинен")):
        return (
            "Активировать антикризисный контур: сценарии ответа, единый пресс-центр, приоритет фактуры и юридической выверки формулировок.",
            "Подготовить держателей линии для СМИ и соцсетей, пакет тезисов и запретные формулировки; провести внутренний бриф.",
            "Усилить мониторинг и алерты по теме; при необходимости — опережающее письмо редакторам или пост-разъяснение в доверенных каналах.",
        )
    return (
        "Сформировать PR-пакет: Q&A, тезисы для спикера, приоритетные каналы и форматы коммуникации; согласовать линию с юридическим и комплаенс-блоком при необходимости.",
        "Протестировать ключевые формулировки на понятность и отсутствие двусмысленностей; доработать месседжи о доверии и прозрачности под выявленные в интервью опасения.",
        "Запланировать мониторинг темы в медиа и соцсетях и следующий цикл согласования коммуникационных шагов.",
    )


def _pr_sanitize_analytical_item(item: dict[str, Any]) -> dict[str, Any]:
    """Убирает или переписывает продуктовые рекомендации в PR-рамку."""
    out = dict(item)
    if not _item_has_product_advice(out):
        return out
    main, team, follow = _pr_template_bundle(_item_blob(out))
    out["recommendation"] = main
    out["pr_action"] = team
    out["comms_follow_up"] = follow
    # Если продуктовый язык просочился в другие поля — смягчаем без второго вызова LLM
    for key in (
        "comms_signal",
        "pr_relevance",
        "reputation_gap",
        "insight_fact",
        "pr_risk_why",
        "message_what_to_say",
        "channel_where",
        "tone_format_how",
        "finding",
        "explanation",
        "forecast",
    ):
        val = out.get(key)
        if isinstance(val, str) and _PRODUCT_ADVICE_RE.search(val):
            cleaned = _PRODUCT_ADVICE_RE.sub(" ", val)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if len(cleaned) < 50:
                out[key] = (
                    "Сигнал интервью относится к зоне доверия и восприятия бренда; "
                    "детальная интерпретация — в полях коммуникационного сигнала и PR-действий."
                )
            else:
                out[key] = cleaned
    val_imp = out.get("impact")
    if isinstance(val_imp, str) and _PRODUCT_ADVICE_RE.search(val_imp):
        out["impact"] = (
            "Растёт риск для репутации и доверия к нарративу бренда; внешние коммуникации могут расходиться с ожиданиями аудитории — "
            "это зона ответственности PR и корпоративных коммуникаций."
        )
    val_chain = out.get("causal_chain")
    if isinstance(val_chain, str) and _PRODUCT_ADVICE_RE.search(val_chain):
        out["causal_chain"] = "Сигнал в интервью → восприятие и доверие к бренду → риск для репутации и медиаполя"
    return out


def _pr_sanitize_next_step_item(step: dict[str, Any]) -> dict[str, Any]:
    out = dict(step)
    t = str(out.get("text", "") or "")
    if _PRODUCT_ADVICE_RE.search(t):
        out["text"] = (
            "Согласовать с PR и корпоративными коммуникациями линию сообщений и Q&A; "
            "определить каналы донесения и формат ответов без предложений по изменению продукта."
        )
        if out.get("rationale"):
            out["rationale"] = "Шаг заменён на коммуникационный из-за политики отчёта (только PR-уровень)."
    return out


def _pr_sanitize_executive_summary(text: str) -> str:
    if not (text and text.strip()):
        return text
    if not _PRODUCT_ADVICE_RE.search(text):
        return text
    chunks = re.split(r"(?<=[.!?…])\s+", text.strip())
    kept = [c for c in chunks if c and not _PRODUCT_ADVICE_RE.search(c)]
    out = " ".join(kept).strip()
    if len(out) < 80:
        out = (
            "По материалам интервью ключевой фокус для PR — доверие, прозрачность коммуникаций и выбор каналов, которым аудитория доверяет. "
            "Продуктовые изменения в отчёт не входят: дальнейшие шаги — в блоках рекомендаций и next_steps на стороне коммуникаций."
        )
    return out


def _rebuild_item_display_text(item: dict[str, Any]) -> dict[str, Any]:
    item["text"] = _compose_display_text(item)
    return item


def _item_is_meaningful(item: dict[str, Any]) -> bool:
    t = str(item.get("text", "") or "").strip()
    if len(t) >= 40:
        return True
    f = str(item.get("finding", "") or "").strip()
    return len(f) >= 40


def _pr_sanitize_plain_line(line: str) -> str:
    t = line.strip()
    if not t:
        return t
    if _PRODUCT_ADVICE_RE.search(t):
        return (
            "Согласовать линию PR и Q&A по теме доверия; определить каналы ответов без предложений по изменению продукта."
        )
    return t


def _apply_pr_postprocess(rep: ResearchReport) -> None:
    """Фильтр и переписывание продуктового языка в PR-рамку; сохраняет структуру JSON для UI."""
    rep.executive_summary = _pr_sanitize_executive_summary(rep.executive_summary)

    for attr in (
        "key_findings_json",
        "problems_json",
        "patterns_json",
        "risks_json",
        "hypotheses_json",
        "recommendations_json",
        "forecast_json",
    ):
        raw = getattr(rep, attr, None)
        lst = _as_list(raw)
        new_lst: list[Any] = []
        for it in lst:
            if not isinstance(it, dict):
                new_lst.append(it)
                continue
            cleaned = _pr_sanitize_analytical_item(it)
            cleaned = _rebuild_item_display_text(cleaned)
            if _item_is_meaningful(cleaned):
                new_lst.append(cleaned)
        setattr(rep, attr, new_lst)

    ns = _as_list(rep.next_steps_json)
    rep.next_steps_json = [
        _pr_sanitize_next_step_item(x) if isinstance(x, dict) else x for x in ns if x
    ]

    extras = getattr(rep, "report_extras_json", None)
    if isinstance(extras, dict):
        tps = extras.get("talking_points")
        if isinstance(tps, list):
            extras["talking_points"] = [_pr_sanitize_plain_line(str(x)) for x in tps if str(x).strip()]
        inf = extras.get("infopovody")
        if isinstance(inf, list):
            extras["infopovody"] = [_pr_sanitize_plain_line(str(x)) for x in inf if str(x).strip()]
        oq = extras.get("open_questions")
        if isinstance(oq, list):
            extras["open_questions"] = [_pr_sanitize_plain_line(str(x)) for x in oq if str(x).strip()]
        for key in ("reputational_risks", "communication_gaps", "next_steps_pr"):
            raw_list = extras.get(key)
            if isinstance(raw_list, list):
                extras[key] = [_pr_sanitize_plain_line(str(x)) for x in raw_list if str(x).strip()]
        wa = extras.get("word_analysis")
        if isinstance(wa, dict):
            dlx = wa.get("dominant_lexicon_pr_perception")
            if isinstance(dlx, str) and dlx.strip():
                wa["dominant_lexicon_pr_perception"] = _pr_sanitize_plain_line(dlx)
            extras["word_analysis"] = wa
        rep.report_extras_json = extras


def _merge_grounded_in(item: dict[str, Any]) -> list[str]:
    raw = item.get("grounded_in")
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        if out:
            return out
    alt = item.get("evidence_unit_ids")
    if isinstance(alt, list):
        return [str(x).strip() for x in alt if str(x).strip()]
    return []


def _compose_display_text(item: dict[str, Any]) -> str:
    """Build readable 'text' for stored JSON / UI if model omitted or shortened it."""
    parts: list[str] = []
    for key, label in (
        ("comms_signal", "Сигнал для PR"),
        ("pr_relevance", "Значимость для PR"),
        ("reputation_gap", "Репутационный разрыв или коммуникационный зазор"),
        ("pr_action", "Ответ PR-команды"),
        ("comms_follow_up", "Следующий шаг в коммуникациях"),
        ("insight_fact", "Что происходит (инсайт)"),
        ("pr_risk_why", "Почему это риск для PR"),
        ("message_what_to_say", "Что говорить"),
        ("channel_where", "Где говорить"),
        ("tone_format_how", "Как говорить (тон и формат)"),
        ("finding", None),
        ("explanation", None),
        ("causal_chain", "Цепочка"),
        ("impact", None),
        ("recommendation", None),
        ("forecast", "Прогноз"),
    ):
        v = item.get(key)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s:
            continue
        if label:
            parts.append(f"{label}: {s}")
        else:
            parts.append(s)
    return "\n\n".join(parts).strip()


def _normalize_analytical_item(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return {"text": raw.strip(), "grounded_in": []}
    if not isinstance(raw, dict):
        return {"text": str(raw), "grounded_in": []}
    item = dict(raw)
    item["grounded_in"] = _merge_grounded_in(item)
    text = item.get("text")
    if not isinstance(text, str) or len(text.strip()) < 120:
        composed = _compose_display_text(item)
        if composed:
            item["text"] = composed
        elif isinstance(text, str):
            item["text"] = text.strip()
        else:
            item["text"] = ""
    else:
        item["text"] = text.strip()
    return item


def _normalize_next_step(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        s = raw.strip()
        return {"text": s} if s else {}
    if isinstance(raw, dict):
        t = str(raw.get("text") or raw.get("step") or "").strip()
        r = str(raw.get("rationale") or raw.get("why") or "").strip()
        if not t:
            return {}
        if r:
            return {"text": f"{t}\n\nЗачем: {r}", "rationale": r}
        return {"text": t}
    return {}


def _normalize_section_list(key: str, raw: Any) -> list[Any]:
    items = _as_list(raw)
    if key == "next_steps":
        out = []
        for it in items:
            n = _normalize_next_step(it)
            if n:
                out.append(n)
        return out
    if key in _ANALYTICAL_SECTION_KEYS:
        return [_normalize_analytical_item(it) for it in items if it]
    return items


def _debug_log_report_build(
    *,
    settings: Settings,
    project_id: UUID,
    report_id: UUID,
    canonical_total: int,
    in_prompt: int,
    by_type: dict[str, int],
    recurring_n: int,
    quotes_n: int,
    section_counts: dict[str, int],
    report_language: str | None = None,
    synthesis_meta: dict[str, int] | None = None,
) -> None:
    if not settings.research_report_generation_debug:
        return
    logger.info(
        "research_report_generation_debug project_id=%s report_id=%s "
        "canonical_entities=%s prompt_units=%s by_type=%s recurring_themes=%s quote_pool=%s sections=%s "
        "report_language=%s synthesis_meta=%s",
        project_id,
        report_id,
        canonical_total,
        in_prompt,
        by_type,
        recurring_n,
        quotes_n,
        section_counts,
        report_language,
        synthesis_meta,
    )


class ResearchReportGenerationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_generating_report_sync(
        self,
        session: Session,
        project_id: UUID,
        *,
        stage: str = "preparing",
    ) -> ResearchReport:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError("project_not_found")
        rep = ResearchReport(
            project_id=project_id,
            status=ReportStatus.GENERATING,
            title=project.name,
            description=None,
            executive_summary="",
            report_extras_json={"stage": stage},
        )
        session.add(rep)
        session.flush()
        return rep

    def mark_report_stage_sync(
        self,
        session: Session,
        report_id: UUID,
        *,
        stage: str,
        extra: dict[str, Any] | None = None,
    ) -> ResearchReport | None:
        rep = session.get(ResearchReport, report_id)
        if rep is None:
            return None
        extras = dict(rep.report_extras_json or {})
        extras["stage"] = stage
        if extra:
            extras.update(extra)
        rep.status = ReportStatus.GENERATING
        rep.report_extras_json = extras
        session.flush()
        return rep

    def mark_report_failed_sync(
        self,
        session: Session,
        report_id: UUID,
        *,
        error_code: str,
        error_message: str,
        extra: dict[str, Any] | None = None,
    ) -> ResearchReport | None:
        rep = session.get(ResearchReport, report_id)
        if rep is None:
            return None
        extras = dict(rep.report_extras_json or {})
        extras.update(
            {
                "stage": "failed",
                "error_code": error_code,
                "error_message": error_message[:1000],
            }
        )
        if extra:
            extras.update(extra)
        rep.status = ReportStatus.FAILED
        rep.report_extras_json = extras
        session.flush()
        return rep

    def generate_for_project_sync(
        self,
        session: Session,
        project_id: UUID,
        *,
        report_id: UUID | None = None,
    ) -> ResearchReport:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError("project_not_found")

        key = (self._settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("openai_api_key_required_for_research_report")

        canonicals = list(
            session.scalars(
                select(ExtractedEntity)
                .where(
                    ExtractedEntity.project_id == project_id,
                    ExtractedEntity.canonical_entity_id.is_(None),
                )
                .order_by(ExtractedEntity.created_at.asc())
                .limit(_MAX_CANONICAL_LOAD)
            ).all()
        )

        synthesis_entities = _select_synthesis_entities(canonicals)
        selected = _select_prompt_entities(synthesis_entities)
        recurring = _recurring_themes(synthesis_entities)
        quote_pool = _quotes_from_entities(synthesis_entities)
        snapshot = _load_snapshot(session, project_id)
        snapshot_trimmed = _trim_json_value(snapshot, _MAX_SNAPSHOT_JSON_CHARS)

        brand = (self._settings.research_report_brand_name or "Click").strip() or "Click"
        synthesis_input = build_smart_report_input(
            project=project,
            canonical_entities=synthesis_entities,
            aggregation_snapshot=snapshot_trimmed,
            brand_name=brand,
        )
        report_language = str(synthesis_input.get("report_language") or "ru")
        themes = _merge_theme_lists(
            [str(x) for x in (synthesis_input.get("external_research_seeds") or []) if str(x).strip()],
            _infer_search_themes(canonicals),
        )
        ext = get_external_research_provider(self._settings)
        draft_articles = ext.search_sync(
            themes=themes,
            context=project.description or project.name,
            language=report_language,
        )

        if report_id is not None:
            rep = session.get(ResearchReport, report_id)
            if rep is None:
                raise ValueError("report_not_found")
            rep.status = ReportStatus.GENERATING
            rep.title = project.name
            rep.executive_summary = rep.executive_summary or ""
            rep.report_extras_json = {**dict(rep.report_extras_json or {}), "stage": "generating_report"}
        else:
            rep = ResearchReport(
                project_id=project_id,
                status=ReportStatus.GENERATING,
                title=project.name,
                description=None,
                executive_summary="",
                report_extras_json={"stage": "generating_report"},
            )
            session.add(rep)
        session.flush()

        logger.info(
            "ResearchReport smart_synthesis project_id=%s report_id=%s report_language=%s brand=%s "
            "provider=%s canonical_entities=%s index_entities=%s recurring_patterns=%s evidence_quotes=%s themes=%s",
            project_id,
            rep.id,
            report_language,
            brand,
            ext.__class__.__name__,
            len(synthesis_entities),
            len(selected),
            len(synthesis_input.get("recurring_patterns") or []),
            len(synthesis_input.get("evidence_quotes") or []),
            len(themes),
        )

        entity_index = _canonical_entity_index(selected)
        if report_language == "ru":
            instructions = (
                f"Сформируй отчёт в режиме smart synthesis. report_language=ru — весь смысловой текст на русском. "
                f"Бренд «{brand}»; не подменять. Только PR и коммуникации; заземляй выводы в synthesis_input и цитатах; "
                "не пересказывай интервью целиком."
            )
        else:
            instructions = (
                f"Smart synthesis. report_language=en — analytical narrative in English. "
                f"Brand «{brand}»; do not swap. PR/comms only; ground claims in synthesis_input and quotes."
            )

        user_payload: dict[str, Any] = {
            "analysis_mode": "smart_synthesis",
            "report_language": report_language,
            "instructions": instructions,
            "synthesis_input": synthesis_input,
            "canonical_entity_index": entity_index,
            "draft_external_articles": draft_articles,
            "unit_counts_by_type": _type_counts(synthesis_entities),
        }
        prompt_limit = self._settings.pr_report_max_prompt_chars or _DEFAULT_MAX_USER_JSON_CHARS
        user = _bounded_user_payload_json(user_payload, max_chars=prompt_limit)

        client = OpenAI(api_key=key, timeout=180.0)
        system_prompt = _build_report_system(brand, report_language)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ]
        data: dict[str, Any] = {}
        last_raw: str | None = None
        max_attempts = 1 + self._settings.pr_report_max_repair_attempts
        validation_errors: list[str] = []
        for attempt in range(max_attempts):
            try:
                completion = client.chat.completions.create(
                    model=self._settings.openai_report_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.36 if attempt == 0 else 0.2,
                )
            except Exception:
                rep.status = ReportStatus.FAILED
                session.flush()
                logger.exception("ResearchReport GPT failed project_id=%s", project_id)
                raise

            raw = completion.choices[0].message.content if completion.choices else None
            if not raw:
                rep.status = ReportStatus.FAILED
                session.flush()
                raise RuntimeError("empty_report_llm_response")
            last_raw = raw
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                rep.status = ReportStatus.FAILED
                session.flush()
                raise RuntimeError(f"invalid_report_json: {e}") from e

            validation_errors = _report_data_validation_errors(data, report_language=report_language)
            if not validation_errors:
                break
            logger.warning(
                "ResearchReport PR/English validation failed project_id=%s report_language=%s attempt=%s/%s",
                project_id,
                report_language,
                attempt + 1,
                max_attempts,
            )
            messages.append({"role": "user", "content": _regeneration_user_hint(brand, report_language, validation_errors)})
        else:
            logger.warning(
                "ResearchReport PR validation still failing after retries project_id=%s errors=%s draft_prefix=%r",
                project_id,
                validation_errors,
                (last_raw or "")[:400],
            )

        rep.title = str(data.get("title") or project.name)[:2000]
        rep.description = str(data.get("description") or "").strip() or None
        rep.executive_summary = str(data.get("executive_summary") or "").strip()
        rep.key_findings_json = _normalize_section_list("key_findings", data.get("key_findings"))
        rep.problems_json = _normalize_section_list("problems", data.get("problems"))
        rep.patterns_json = _normalize_section_list("patterns", data.get("patterns"))
        rep.risks_json = _normalize_section_list("risks", data.get("risks"))
        rep.hypotheses_json = _normalize_section_list("hypotheses", data.get("hypotheses"))
        rep.recommendations_json = _normalize_section_list("recommendations", data.get("recommendations"))
        rep.forecast_json = _normalize_section_list("forecast", data.get("forecast"))
        rep.next_steps_json = _normalize_section_list("next_steps", data.get("next_steps"))
        rep.external_articles_json = _normalize_external_articles_list(data.get("external_articles"), draft_articles)
        rep.supporting_quotes_json = _as_list(data.get("supporting_quotes"))
        wf_builder = synthesis_input.get("word_frequency_block")
        merged_wa = _merge_word_analysis(
            wf_builder if isinstance(wf_builder, dict) else {},
            data.get("word_analysis"),
        )
        rep.report_extras_json = {
            "talking_points": _normalize_talking_points(data.get("talking_points")),
            "reputational_risks": _normalize_pr_bullet_list(data.get("reputational_risks")),
            "communication_gaps": _normalize_pr_bullet_list(data.get("communication_gaps")),
            "next_steps_pr": _normalize_pr_bullet_list(data.get("next_steps_pr"), max_items=14),
            "infopovody": _normalize_short_string_list(data.get("infopovody"), max_items=10),
            "open_questions": _normalize_short_string_list(data.get("open_questions"), max_items=12),
            "word_analysis": merged_wa,
        }
        _apply_pr_postprocess(rep)
        rep.status = ReportStatus.READY
        session.flush()

        section_counts = {
            "key_findings": len(_as_list(rep.key_findings_json)),
            "problems": len(_as_list(rep.problems_json)),
            "patterns": len(_as_list(rep.patterns_json)),
            "risks": len(_as_list(rep.risks_json)),
            "hypotheses": len(_as_list(rep.hypotheses_json)),
            "recommendations": len(_as_list(rep.recommendations_json)),
            "forecast": len(_as_list(rep.forecast_json)),
            "next_steps": len(_as_list(rep.next_steps_json)),
            "supporting_quotes": len(_as_list(rep.supporting_quotes_json)),
            "external_articles": len(_as_list(rep.external_articles_json)),
            "talking_points": len(_as_list((rep.report_extras_json or {}).get("talking_points"))),
        }
        _debug_log_report_build(
            settings=self._settings,
            project_id=project_id,
            report_id=rep.id,
            canonical_total=len(canonicals),
            in_prompt=len(selected),
            by_type=_type_counts(selected),
            recurring_n=len(recurring),
            quotes_n=len(quote_pool),
            section_counts=section_counts,
            report_language=report_language,
            synthesis_meta={
                "recurring_patterns": len(synthesis_input.get("recurring_patterns") or []),
                "evidence_quotes": len(synthesis_input.get("evidence_quotes") or []),
                "key_signals": len(synthesis_input.get("key_signals") or []),
            },
        )

        logger.info(
            "ResearchReport ready project_id=%s report_id=%s model=%s report_language=%s brand=%s",
            project_id,
            rep.id,
            self._settings.openai_report_model,
            report_language,
            brand,
        )
        return rep


def get_research_report_generation_service(settings: Settings | None = None) -> ResearchReportGenerationService:
    return ResearchReportGenerationService(settings=settings)
