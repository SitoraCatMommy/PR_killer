"""Data-first gates: when LLM synthesis is allowed, coverage score, and user-facing messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _t(lang: str, ru: str, uz: str, en: str) -> str:
    lg = (lang or "ru").strip().lower()[:8]
    if lg == "uz":
        return uz
    if lg == "en":
        return en
    return ru


@dataclass(frozen=True)
class QualityGateItem:
    """One row for the diagnostic checklist (UI + API)."""

    id: str
    label: str
    passed: bool
    current: float
    threshold: float
    unit: str = "count"


@dataclass(frozen=True)
class DataReadiness:
    """Aggregated from extracted entities and interview counts (no model calls)."""

    data_coverage_score: float
    can_synthesize: bool
    warnings: list[str]
    user_message: str
    # Factors for API consumers
    interview_count: int
    has_entity_signal: bool
    quote_count: int


# --- Strict PR decision / strategy gates (DATA → INSIGHT → ACTION) ---
MIN_INTERVIEWS_STRICT = 10
MIN_ENTITY_ROWS_STRICT = 50
MIN_EVIDENCE_QUOTES_STRICT = 12
MIN_RISK_PROBLEM_VOLUME_STRICT = 18  # sum of bar ``value`` for problems + risks


@dataclass(frozen=True)
class StrictPRReadiness:
    """All must pass before portrait / PR strategy / compare LLM layers run."""

    ready: bool
    checklist: list[QualityGateItem]
    user_message: str


def _bar_volume(rows: Any) -> int:
    if not isinstance(rows, list):
        return 0
    return sum(int((x or {}).get("value") or 0) for x in rows if isinstance(x, dict))


def assess_strict_pr_readiness(
    ctx: dict[str, Any],
    *,
    output_language: str = "ru",
) -> StrictPRReadiness:
    """
    Hard gates for AI insight + action layers.

    Expects ctx with: interview_count, topics_pie, problems_bar, risks_bar, quotes (list),
    entity_row_count (optional), evidence_quotes_count (optional; else len(quotes)).
    """
    ic = int(ctx.get("interview_count") or 0)
    ent_n = int(ctx.get("entity_row_count") if ctx.get("entity_row_count") is not None else -1)
    if ent_n < 0:
        ent_n = 0
    qlist = ctx.get("quotes") or []
    eq = int(ctx.get("evidence_quotes_count") if ctx.get("evidence_quotes_count") is not None else len(qlist))
    prb = _bar_volume(ctx.get("problems_bar"))
    rsk = _bar_volume(ctx.get("risks_bar"))
    vol = prb + rsk

    items: list[QualityGateItem] = [
        QualityGateItem(
            id="interviews",
            label=_t(
                output_language,
                "Интервью (units / источники)",
                "Intervyular",
                "Interviews (units / sources)",
            ),
            passed=ic >= MIN_INTERVIEWS_STRICT,
            current=float(ic),
            threshold=float(MIN_INTERVIEWS_STRICT),
        ),
        QualityGateItem(
            id="entities",
            label=_t(
                output_language,
                "Извлечённые сущности (строки)",
                "Ajratilgan obyektlar",
                "Extracted entity rows",
            ),
            passed=ent_n >= MIN_ENTITY_ROWS_STRICT,
            current=float(ent_n),
            threshold=float(MIN_ENTITY_ROWS_STRICT),
        ),
        QualityGateItem(
            id="evidence_quotes",
            label=_t(
                output_language,
                "Доказательные цитаты",
                "Iqtiboslar",
                "Evidence quotes",
            ),
            passed=eq >= MIN_EVIDENCE_QUOTES_STRICT,
            current=float(eq),
            threshold=float(MIN_EVIDENCE_QUOTES_STRICT),
        ),
        QualityGateItem(
            id="risk_problem_signals",
            label=_t(
                output_language,
                "Сигналы проблем и рисков (объём по данным)",
                "Muammo va xavf signallari",
                "Problem + risk signal volume",
            ),
            passed=vol >= MIN_RISK_PROBLEM_VOLUME_STRICT,
            current=float(vol),
            threshold=float(MIN_RISK_PROBLEM_VOLUME_STRICT),
        ),
    ]
    ready = all(x.passed for x in items)
    msg = "" if ready else _t(
        output_language,
        "Набор данных ещё не готов для слоя инсайтов и действий: выполните чеклист ниже (интервью, извлечение, цитаты).",
        "Insight va harakat qatlami uchun maʼlumotlar toʻliq emas — pastdagi roʻyxatni bajaring.",
        "Dataset is not yet ready for insight and action layers — complete the checklist below.",
    )
    return StrictPRReadiness(ready=ready, checklist=items, user_message=msg)


def insufficient_synthesis_message(output_language: str) -> str:
    return _t(
        output_language,
        "Недостаточно данных для вывода. Загрузите и обработайте интервью (и дождитесь извлечения сущностей), "
        "затем сформируйте отчёт снова.",
        "Xulosa uchun yetarli maʼlumot yo'q. Intervʼyularni yuklang va tahlil tugashini kuting, keyin qayta urining.",
        "Not enough data to draw conclusions. Upload and process interviews (wait for entity extraction), then retry.",
    )


def build_data_warnings(ctx: dict[str, Any], *, min_interviews_warn: int = 10) -> list[str]:
    out: list[str] = []
    ic = int(ctx.get("interview_count") or 0)
    topics = len(ctx.get("topics_pie") or [])
    probs = len(ctx.get("problems_bar") or [])
    risks = len(ctx.get("risks_bar") or [])
    nq = len(ctx.get("quotes") or [])

    if ic < 1:
        out.append("Нет интервью в выборке — аналитика пуста.")
    elif ic < min_interviews_warn:
        out.append(
            f"Мало интервью ({ic}): для устойчивых выводов обычно нужна более широкая выборка (ориентир — от {min_interviews_warn})."
        )
    if topics + probs + risks < 1 and nq < 1:
        out.append(
            "Нет извлечённых тем, проблем, рисков и цитат — проверьте, что источники обработаны (очередь, извлечение сущностей)."
        )
    elif topics + probs + risks < 1 and nq >= 1:
        out.append("Мало структурированных тем/проблем/рисков — оценка опирается в основном на цитаты и частоту слов.")
    return out


def assess_synthesis_readiness(
    ctx: dict[str, Any],
    *,
    output_language: str = "ru",
) -> DataReadiness:
    """
    ``can_synthesize`` is False when there is no groundable research signal
    (no interviews, or no entities/topics/problems/risks and no quotes).
    """
    ic = int(ctx.get("interview_count") or 0)
    tpc = len(ctx.get("topics_pie") or [])
    prb = len(ctx.get("problems_bar") or [])
    rsk = len(ctx.get("risks_bar") or [])
    nq = len(ctx.get("quotes") or [])
    pat = len(ctx.get("top_patterns") or [])
    ins = len(ctx.get("top_insights") or [])

    has_bar_signal = tpc + prb + rsk > 0
    has_support = nq > 0 or pat > 0 or ins > 0
    has_entity_signal = has_bar_signal or has_support

    if ic < 1:
        can_syn = False
    elif not has_entity_signal:
        can_syn = False
    else:
        can_syn = True

    # 0..1 score: volume + diversity of signals
    w_ic = min(1.0, ic / 12.0) * 0.3
    w_bars = min(1.0, (tpc + prb + rsk) / 18.0) * 0.35
    w_q = min(1.0, nq / 16.0) * 0.25
    w_misc = min(1.0, (pat + ins) / 14.0) * 0.1
    data_coverage = round(min(1.0, w_ic + w_bars + w_q + w_misc), 2)
    if not can_syn:
        data_coverage = round(min(data_coverage, 0.2), 2)

    msg = "" if can_syn else insufficient_synthesis_message(output_language)
    warnings = build_data_warnings(ctx)

    return DataReadiness(
        data_coverage_score=data_coverage,
        can_synthesize=can_syn,
        warnings=warnings,
        user_message=msg,
        interview_count=ic,
        has_entity_signal=has_entity_signal,
        quote_count=nq,
    )
