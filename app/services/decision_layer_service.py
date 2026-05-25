"""Decision layer: priority actions, impact/effort matrix, alerts — PR strategy enrichment + segment-compare."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from openai import OpenAI

from app.infrastructure.settings import Settings, get_settings
from app.schemas.decision_layer import DecisionAlertItem

logger = logging.getLogger(__name__)

_LEVELS = frozenset({"high", "medium", "low"})
_ALERT_TYPES = frozenset({"risk", "sentiment", "trust"})
_ALERT_SEV = frozenset({"high", "medium"})


def _norm_level(v: object) -> str:
    s = str(v or "").strip().lower()
    return s if s in _LEVELS else "medium"


def _norm_alert_type(v: object) -> str:
    s = str(v or "").strip().lower()
    return s if s in _ALERT_TYPES else "risk"


def _norm_severity(v: object) -> str:
    s = str(v or "").strip().lower()
    return s if s in _ALERT_SEV else "medium"


def parse_priority_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for it in raw[:24]:
        if not isinstance(it, dict):
            continue
        action = str(it.get("action") or "").strip()
        if not action:
            continue
        bo = it.get("based_on") if isinstance(it.get("based_on"), list) else []
        based_on = [str(x).strip() for x in bo if str(x).strip()][:24]
        out.append(
            {
                "action": action[:500],
                "impact": _norm_level(it.get("impact")),
                "effort": _norm_level(it.get("effort")),
                "reason": str(it.get("reason") or "").strip()[:900],
                "based_on": based_on,
            }
        )
    return out


def parse_alerts(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for it in raw[:16]:
        if not isinstance(it, dict):
            continue
        msg = str(it.get("message") or "").strip()
        if not msg:
            continue
        out.append(
            {
                "type": _norm_alert_type(it.get("type")),
                "message": msg[:600],
                "severity": _norm_severity(it.get("severity")),
            }
        )
    return out


def build_impact_effort_matrix(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "action": a.get("action", ""),
            "impact": a.get("impact", "medium"),
            "effort": a.get("effort", "medium"),
        }
        for a in actions
    ]


def _t(lang: str, ru: str, uz: str, en: str) -> str:
    lg = (lang or "ru").strip().lower()[:8]
    if lg == "uz":
        return uz
    if lg == "en":
        return en
    return ru


def heuristic_alerts_from_strategy_and_ctx(
    strategy: dict[str, Any],
    ctx: dict[str, Any],
    *,
    output_language: str,
) -> list[dict[str, Any]]:
    """Rule-based alerts: frequency in risks_bar, negative sentiment, repeated risk themes."""
    lang = (output_language or "ru").strip().lower()[:8]
    alerts: list[dict[str, Any]] = []

    sent = ctx.get("sentiment") or {}
    neg = int(sent.get("negative_signals") or 0)
    pos = int(sent.get("positive_signals") or 0)
    bal = str(sent.get("balance") or "").lower()
    if bal == "negative" or (neg > 0 and pos > 0 and neg >= pos * 1.4):
        sev = "high" if neg >= max(10, pos * 2) or bal == "negative" else "medium"
        alerts.append(
            {
                "type": "sentiment",
                "message": _t(
                    lang,
                    f"Перекос в негативных сигналах: {neg} нег. vs {pos} поз. — проверьте тон коммуникаций и факты.",
                    f"Negativ signallar ustun: {neg} vs {pos} — ton va dalillar.",
                    f"Negative sentiment skew: {neg} vs {pos} positive — review tone and evidence.",
                ),
                "severity": sev,
            }
        )

    risks_bar = ctx.get("risks_bar") or []
    rep_risks = [str(x).strip().lower() for x in (strategy.get("reputational_risks") or []) if str(x).strip()]
    for row in risks_bar[:8]:
        if not isinstance(row, dict):
            continue
        lab = str(row.get("label") or "").strip()
        val = int(row.get("value") or 0)
        if not lab or val < 4:
            continue
        lab_l = lab.lower()
        repeated = any(lab_l in rr or rr in lab_l for rr in rep_risks if len(rr) > 6)
        if val >= 8 or repeated:
            sev = "high" if val >= 10 or repeated else "medium"
            alerts.append(
                {
                    "type": "risk",
                    "message": _t(
                        lang,
                        f"Частый риск/напряжённая тема «{lab[:120]}» (×{val})"
                        + (" — совпадает с репутационными рисками стратегии" if repeated else "")
                        + ".",
                        f"Takrorlanuvchi xavf: «{lab[:120]}» (×{val}).",
                        f"Frequent risk theme “{lab[:120]}” (×{val})"
                        + (" — overlaps strategy risks" if repeated else "")
                        + ".",
                    ),
                    "severity": sev,
                }
            )

    insights = ctx.get("top_insights") or []
    trust_n = sum(
        1
        for x in insights
        if isinstance(x, dict)
        and (
            str(x.get("pr_signal_type") or "").lower() == "trust_driver"
            or str(x.get("type") or "").lower() in ("trust_issue", "trust")
        )
    )
    if trust_n >= 2:
        alerts.append(
            {
                "type": "trust",
                "message": _t(
                    lang,
                    f"Несколько сигналов доверия/напряжения в инсайтах ({trust_n}) — усилить proof и прозрачность.",
                    f"Ishonch bilan bog'liq {trust_n} ta signal — ishonchlilikni mustahkamlang.",
                    f"{trust_n} trust-related insight signals — strengthen proof and transparency.",
                ),
                "severity": "medium" if trust_n < 4 else "high",
            }
        )

    return alerts


def merge_alerts(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    *,
    limit: int = 14,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for src in (primary, secondary):
        for a in src:
            key = (str(a.get("type")), re.sub(r"\s+", " ", str(a.get("message") or "").lower()[:72]))
            if key in seen:
                continue
            seen.add(key)
            try:
                out.append(DecisionAlertItem.model_validate(a).model_dump())
            except Exception:
                continue
            if len(out) >= limit:
                return out
    return out


def fallback_priority_actions(strategy: dict[str, Any], *, output_language: str) -> list[dict[str, Any]]:
    lang = (output_language or "ru").strip().lower()[:8]
    out: list[dict[str, Any]] = []
    for text, impact, effort in (
        *[(x, "high", "medium") for x in (strategy.get("reputational_risks") or [])[:2]],
        *[(x, "medium", "low") for x in (strategy.get("next_steps") or [])[:5]],
    ):
        t = str(text).strip()
        if not t:
            continue
        out.append(
            {
                "action": t[:400],
                "impact": impact,
                "effort": effort,
                "based_on": [],
                "reason": _t(
                    lang,
                    "Выведено из стратегии (риски / следующие шаги) при отсутствии явного блока priority_actions от модели.",
                    "Strategiyadan (xavf / keyingi qadamlar).",
                    "Derived from strategy risks/next steps when model omitted priority_actions.",
                ),
            }
        )
        if len(out) >= 8:
            break
    return out


def enrich_strategy_decision_layer(
    strategy: dict[str, Any],
    ctx: dict[str, Any],
    *,
    output_language: str,
) -> None:
    """Mutates `strategy` with normalized priority_actions, impact_effort_matrix, merged alerts."""
    lang = (output_language or "ru").strip().lower()[:8]
    actions = parse_priority_actions(strategy.get("priority_actions"))
    if not actions:
        actions = fallback_priority_actions(strategy, output_language=lang)
    strategy["priority_actions"] = actions
    strategy["impact_effort_matrix"] = build_impact_effort_matrix(actions)

    llm_alerts = parse_alerts(strategy.get("alerts"))
    heur = heuristic_alerts_from_strategy_and_ctx(strategy, ctx, output_language=lang)
    strategy["alerts"] = merge_alerts(llm_alerts, heur)


def _decision_compare_system_prompt(output_language: str) -> str:
    if output_language == "uz":
        return (
            "Siz qaror qatlami tahlilchisisiz. Ikki segment taqqoslashi, PR strategiyasi fragmentlari va "
            "farqlar asosida kommunikatsiya uchun ustuvor harakatlar va signal alertlari bering. "
            "Faqat bitta JSON (user kalitlari)."
        )
    if output_language == "en":
        return (
            "You are a decision-layer analyst. From a two-segment comparison, PR strategy excerpts, and "
            "differences, produce prioritized actions and short alerts for comms leadership. "
            "Return a single JSON object with the user-specified keys only."
        )
    return (
        "Ты аналитик слоя решений. По сравнению двух сегментов, фрагментам PR-стратегий и списку отличий "
        "сформируй приоритетные действия и короткие алерты для руководителя коммуникаций. "
        "Только один JSON-объект с ключами из user-сообщения."
    )


def _decision_compare_user_payload(
    *,
    segment_a: str,
    segment_b: str,
    differences: list[dict[str, Any]],
    pr_implications: list[str],
    strategy_a: dict[str, Any],
    strategy_b: dict[str, Any],
    output_language: str,
) -> str:
    def _pick(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "reputational_risks": (d.get("reputational_risks") or [])[:8],
            "communication_gaps": (d.get("communication_gaps") or [])[:6],
            "key_pr_insights": (d.get("key_pr_insights") or [])[:8],
            "next_steps": (d.get("next_steps") or [])[:8],
            "recommended_messages": (d.get("recommended_messages") or [])[:6],
        }

    body = {
        "task": "segment_compare_decision_layer",
        "output_language": output_language,
        "segment_a": segment_a,
        "segment_b": segment_b,
        "differences": differences[:16],
        "pr_implications": pr_implications[:14],
        "strategy_a": _pick(strategy_a),
        "strategy_b": _pick(strategy_b),
        "required_output": {
            "priority_actions": (
                "array of 5–10 objects: {action, impact (high|medium|low), "
                "effort (high|medium|low), reason} — actions that reconcile or exploit segment differences"
            ),
            "alerts": (
                "array of 3–8 objects: {type: risk|sentiment|trust, message, severity: high|medium} "
                "— where segments diverge on risk, tone, or trust"
            ),
        },
    }
    return json.dumps(body, ensure_ascii=False)[:95_000]


def generate_compare_decision_layer_sync(
    *,
    segment_a: str,
    segment_b: str,
    differences: list[dict[str, Any]],
    pr_implications: list[str],
    strategy_a: dict[str, Any],
    strategy_b: dict[str, Any],
    output_language: str,
    settings: Settings,
) -> dict[str, Any]:
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError("openai_api_key_missing")
    lang = (output_language or "ru").strip().lower()[:8]
    if lang not in {"ru", "uz", "en"}:
        lang = "ru"
    user_msg = _decision_compare_user_payload(
        segment_a=segment_a,
        segment_b=segment_b,
        differences=differences,
        pr_implications=pr_implications,
        strategy_a=strategy_a,
        strategy_b=strategy_b,
        output_language=lang,
    )
    client = OpenAI(api_key=key, timeout=120.0)
    completion = client.chat.completions.create(
        model=settings.openai_report_model,
        messages=[
            {"role": "system", "content": _decision_compare_system_prompt(lang)},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.28,
    )
    raw = completion.choices[0].message.content if completion.choices else None
    if not raw:
        raise ValueError("empty_llm_response")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("compare_decision_not_object")
    return {
        "priority_actions": parse_priority_actions(data.get("priority_actions")),
        "alerts": parse_alerts(data.get("alerts")),
    }


def heuristic_alerts_segment_compare(
    *,
    side_a: dict[str, Any],
    side_b: dict[str, Any],
    segment_a: str,
    segment_b: str,
    output_language: str,
) -> list[dict[str, Any]]:
    lang = (output_language or "ru").strip().lower()[:8]
    alerts: list[dict[str, Any]] = []

    def _bal(side: dict[str, Any]) -> str:
        s = side.get("sentiment") or {}
        return str(s.get("balance") or "").lower()

    ba, bb = _bal(side_a), _bal(side_b)
    if ba != bb and ("negative" in (ba, bb) or "positive" in (ba, bb)):
        alerts.append(
            {
                "type": "sentiment",
                "message": _t(
                    lang,
                    f"Разный профиль тональности: «{segment_a}» — {ba or 'n/a'}, «{segment_b}» — {bb or 'n/a'}; "
                    "не используйте одну эмоциональную подачу для обеих групп.",
                    f"Sentiment farqi: «{segment_a}» / «{segment_b}».",
                    f"Sentiment profile differs: {segment_a} ({ba or 'n/a'}) vs {segment_b} ({bb or 'n/a'}); "
                    "avoid one emotional frame for both.",
                ),
                "severity": "high" if "negative" in (ba, bb) else "medium",
            }
        )

    ra = [str((r or {}).get("label") or "").strip().lower() for r in (side_a.get("risk_frequency") or [])[:6]]
    rb = [str((r or {}).get("label") or "").strip().lower() for r in (side_b.get("risk_frequency") or [])[:6]]
    ca = Counter(ra)
    cb = Counter(rb)
    overlap = [k for k in ca if k and k in cb and len(k) > 4][:3]
    if overlap:
        alerts.append(
            {
                "type": "risk",
                "message": _t(
                    lang,
                    f"Повторяющиеся риск-темы в обоих сегментах: {', '.join(overlap)} — единый план мониторинга, "
                    "но разные Q&A по сегментам.",
                    f"Ikkala segmentda takrorlanuvchi xavflar: {', '.join(overlap)}.",
                    f"Recurring risk themes in both segments: {', '.join(overlap)} — one monitoring plan, split Q&A.",
                ),
                "severity": "medium",
            }
        )

    return alerts


def build_compare_decision_payload(
    *,
    priority_actions: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    matrix = build_impact_effort_matrix(priority_actions)
    return {
        "priority_actions": priority_actions,
        "impact_effort_matrix": matrix,
        "alerts": alerts,
    }


def fallback_compare_priority_actions(
    pr_implications: list[str],
    differences: list[dict[str, Any]],
    *,
    output_language: str,
) -> list[dict[str, Any]]:
    lang = (output_language or "ru").strip().lower()[:8]
    out: list[dict[str, Any]] = []
    for p in pr_implications[:6]:
        t = str(p).strip()
        if not t:
            continue
        out.append(
            {
                "action": t[:480],
                "impact": "medium",
                "effort": "medium",
                "reason": _t(
                    lang,
                    "На основе PR-импликаций сравнения сегментов (fallback).",
                    "Segment taqqoslash PR-implikatsiyalari.",
                    "From segment-compare PR implications (fallback).",
                ),
            }
        )
    for d in differences[:4]:
        if not isinstance(d, dict):
            continue
        dim = str(d.get("dimension") or "").strip()
        summ = str(d.get("summary") or "").strip()[:400]
        if not summ:
            continue
        out.append(
            {
                "action": _t(
                    lang,
                    f"Учесть измерение «{dim}»: {summ[:200]}…",
                    f"«{dim}» bo'yicha: {summ[:200]}…",
                    f"Address dimension “{dim}”: {summ[:200]}…",
                ),
                "impact": "high" if dim in ("risks", "trust", "sentiment") else "medium",
                "effort": "medium",
                "reason": summ[:700],
            }
        )
        if len(out) >= 8:
            break
    if not out:
        out.append(
            {
                "action": _t(
                    lang,
                    "Согласовать отдельные линии коммуникаций для двух сегментов и проверить данные после извлечения сущностей.",
                    "Ikki segment uchun alohida kommunikatsiya liniyalari.",
                    "Align separate comms tracks for both segments and re-check data after entity extraction.",
                ),
                "impact": "medium",
                "effort": "medium",
                "reason": _t(
                    lang,
                    "Недостаточно готовых импликаций для автоматического списка действий.",
                    "Implikatsiyalar yetarli emas.",
                    "Insufficient implications for an auto action list.",
                ),
            }
        )
    return out
