"""PR-oriented lexicon signals: categorized terms/phrases with interview coverage and example quotes."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.services.batch_dashboard_pr import _DASH_STOPWORDS, _TOKEN_RE

LexCategory = Literal["trust", "risk", "convenience", "negative", "money", "brand"]

_CATEGORIES_ORDER: tuple[LexCategory, ...] = (
    "trust",
    "risk",
    "convenience",
    "negative",
    "money",
    "brand",
)

_PR_FILLERS_RU: frozenset[str] = frozenset(
    {
        "ну",
        "типа",
        "как",
        "бы",
        "вообще",
        "просто",
        "там",
        "вот",
        "это",
        "значит",
        "короче",
        "блин",
        "ладно",
        "типу",
        "тип",
        "кароче",
        "короч",
        "ээ",
        "мм",
        "ага",
        "нуу",
        "вобщем",
        "кстати",
        "знаешь",
        "понимаешь",
        "слушай",
        "да",
        "нет",
        "вроде",
        "кажется",
        "наверное",
        "самое",
        "так",
        "тут",
        "ещё",
        "уже",
        "очень",
        "прям",
        "прямо",
    }
)

_PR_FILLERS_UZ: frozenset[str] = frozenset(
    {
        "xa",
        "yo",
        "qani",
        "demak",
        "xoʻp",
        "hop",
        "mayli",
        "shunday",
        "ana",
        "mana",
        "oʻzi",
        "nimaga",
        "qanaqa",
        "nimadir",
        "shekilli",
        "deyman",
        "bilasizmi",
        "tushunarli",
    }
)

_PR_GENERIC: frozenset[str] = frozenset(
    {
        "человек",
        "люди",
        "человека",
        "людей",
        "приложение",
        "приложения",
        "банк",
        "банка",
        "банке",
        "карта",
        "карты",
        "картой",
        "пользоваться",
        "использовать",
        "использую",
        "дело",
        "вещь",
        "вопрос",
        "раз",
        "два",
        "всё",
        "все",
        "время",
        "сегодня",
        "завтра",
        "вчера",
        "год",
        "месяц",
        "неделя",
        "день",
        "час",
        "минута",
        "интервью",
        "ответ",
        "сказал",
        "сказала",
        "говорит",
        "говорят",
        "думаю",
        "думает",
        "знаю",
        "знает",
        "odam",
        "odamlar",
        "ilova",
        "karta",
        "foydalanish",
        "thing",
        "people",
        "person",
        "app",
        "application",
        "time",
        "day",
        "week",
        "year",
        "interview",
    }
)

_PR_STOP_EXTRA: frozenset[str] = frozenset(
    {
        "который",
        "которая",
        "которое",
        "которые",
        "этот",
        "эта",
        "эти",
        "тот",
        "та",
        "те",
        "такой",
        "такая",
        "такие",
        "такое",
        "мой",
        "моя",
        "моё",
        "мои",
        "наш",
        "наша",
        "наше",
        "наши",
        "ваш",
        "ваша",
        "ваше",
        "ваши",
        "их",
        "его",
        "её",
        "ему",
        "ей",
        "ним",
        "них",
        "им",
        "чтобы",
        "где",
        "когда",
        "почему",
        "зачем",
        "сколько",
        "тоже",
        "также",
        "или",
        "либо",
        "только",
        "даже",
        "весь",
        "вся",
        "каждый",
        "любой",
        "самый",
        "более",
        "менее",
        "слишком",
    }
)

_ALL_LEX_STOP: frozenset[str] = frozenset().union(
    _DASH_STOPWORDS,
    _PR_FILLERS_RU,
    _PR_FILLERS_UZ,
    _PR_GENERIC,
    _PR_STOP_EXTRA,
)


def _norm_text(s: str) -> str:
    return (s or "").lower().replace("ё", "е")


def _norm_phrase(s: str) -> str:
    return " ".join(_norm_text(p) for p in s.split())


def _chunk_interview_key(ch: dict[str, Any]) -> str:
    if ch.get("source_document_id"):
        return f"doc:{ch['source_document_id']}"
    if ch.get("transcript_id"):
        return f"tr:{ch['transcript_id']}"
    if ch.get("source_audio_id"):
        return f"aud:{ch['source_audio_id']}"
    return f"ch:{ch.get('id')}"


def _snippet(text: str, needle: str, *, window: int = 140) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    low = _norm_text(t)
    n = _norm_text(needle)
    i = low.find(n)
    if i < 0:
        return t[: window * 2]
    a = max(0, i - window // 2)
    b = min(len(t), i + len(needle) + window // 2)
    frag = t[a:b].replace("\n", " ")
    return frag.strip()[: 480]


def _tokens(text: str) -> list[str]:
    return [_norm_text(w) for w in _TOKEN_RE.findall(text) if len(w) > 2]


_UNIGRAMS: dict[LexCategory, frozenset[str]] = {
    "trust": frozenset(
        {
            "доверие",
            "доверяю",
            "доверяют",
            "надёжный",
            "надежный",
            "надёжно",
            "надежно",
            "безопасно",
            "безопасность",
            "гарантия",
            "гарантируют",
            "уверенность",
            "уверен",
            "уверена",
            "проверенный",
            "проверено",
            "репутация",
            "репутации",
            "честно",
            "прозрачно",
            "прозрачность",
            "ishtiyot",
            "ishonch",
            "xavfsiz",
        }
    ),
    "risk": frozenset(
        {
            "боюсь",
            "страшно",
            "опасно",
            "опасность",
            "мошенники",
            "мошенник",
            "обман",
            "обманывают",
            "ошибка",
            "ошибку",
            "потерять",
            "потерял",
            "блокировка",
            "заблокировали",
            "риск",
            "риски",
            "угроза",
            "опасаюсь",
            "xavf",
            "aldov",
            "firibgar",
            "scam",
            "fraud",
        }
    ),
    "convenience": frozenset(
        {
            "удобно",
            "удобный",
            "удобнее",
            "быстро",
            "быстрее",
            "легко",
            "лёгко",
            "понятно",
            "понятный",
            "доступно",
            "интуитивно",
            "qulay",
            "tez",
            "oson",
            "easy",
            "fast",
            "simple",
        }
    ),
    "negative": frozenset(
        {
            "бесит",
            "сложно",
            "сложный",
            "долго",
            "непонятно",
            "неудобно",
            "раздражает",
            "проблема",
            "проблемы",
            "ужасно",
            "плохо",
            "отвратительно",
            "noqulay",
            "tushunarsiz",
            "annoying",
            "confusing",
            "slow",
        }
    ),
    "money": frozenset(
        {
            "комиссия",
            "комиссии",
            "бесплатно",
            "дорого",
            "дешево",
            "выгодно",
            "кешбэк",
            "кэшбэк",
            "перевод",
            "оплата",
            "платёж",
            "платеж",
            "тариф",
            "стоимость",
            "цена",
            "komissiya",
            "bepul",
            "qimmat",
            "arzon",
            "fee",
            "free",
            "expensive",
            "cashback",
        }
    ),
    "brand": frozenset(
        {
            "слышал",
            "слышала",
            "рекомендовали",
            "рекомендуют",
            "знакомые",
            "отзывы",
            "отзыв",
            "бренд",
            "recommend",
            "reviews",
            "review",
            "heard",
        }
    ),
}

_PHRASES_RAW: list[tuple[str, LexCategory]] = [
    ("не доверяю", "trust"),
    ("не доверяем", "trust"),
    ("не доверяют", "trust"),
    ("боюсь мошенников", "risk"),
    ("боюсь обмана", "risk"),
    ("удобно пользоваться", "convenience"),
    ("без комиссии", "money"),
    ("без комиссия", "money"),
    ("долго грузится", "negative"),
    ("рекомендовали друзья", "brand"),
    ("не понимаю", "negative"),
    ("не понятно", "negative"),
    ("неудобно пользоваться", "negative"),
    ("очень дорого", "money"),
    ("очень удобно", "convenience"),
    ("не безопасно", "risk"),
    ("do not trust", "trust"),
    ("don't trust", "trust"),
    ("no commission", "money"),
    ("loads slowly", "negative"),
    ("friends recommended", "brand"),
]


def _dedupe_phrases(phrases: list[tuple[str, LexCategory]]) -> list[tuple[str, LexCategory]]:
    seen: set[str] = set()
    out: list[tuple[str, LexCategory]] = []
    for p, c in sorted(phrases, key=lambda x: -len(x[0])):
        k = _norm_phrase(p)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append((p, c))
    return out


_PHRASES = _dedupe_phrases(_PHRASES_RAW)


def _light_stem_ru(w: str) -> str:
    if len(w) < 5:
        return w
    for suf in ("ами", "ями", "ах", "ях", "ов", "ев", "ам", "ем", "ом", "ой", "ый", "ая", "ое", "ые", "ие"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)]
    for suf in ("ость", "ение", "ание", "ние"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)]
    return w


def _lemma_key(w: str) -> str:
    w = _norm_text(w)
    if re.search(r"[а-яё]", w):
        return _light_stem_ru(w)
    return w


def build_pr_lexicon_signals_from_chunks(
    chunks: list[dict[str, Any]],
    *,
    interview_count: int,
    brand_tokens: list[str] | None = None,
    top_per_category: int = 14,
) -> dict[str, Any]:
    ic = max(1, int(interview_count or 1))
    brands = {_norm_text(b) for b in (brand_tokens or []) if str(b).strip()}
    brands.discard("")

    brand_unigrams: set[str] = set()
    for b in brands:
        for part in re.split(r"[^\wа-яёА-ЯЁa-zA-Z]+", b):
            t = _norm_text(part)
            if len(t) > 2:
                brand_unigrams.add(t)

    agg: dict[tuple[str, LexCategory], dict[str, Any]] = {}

    def bump(term: str, cat: LexCategory, ch: dict[str, Any], quote: str) -> None:
        key = (term, cat)
        if key not in agg:
            agg[key] = {
                "term": term,
                "category": cat,
                "count": 0,
                "sources": set(),
                "quotes": [],
            }
        a = agg[key]
        a["count"] += 1
        a["sources"].add(_chunk_interview_key(ch))
        if len(a["quotes"]) < 3 and quote:
            tid = str(ch.get("transcript_id") or "")
            cid = str(ch.get("id") or "")
            a["quotes"].append({"quote": quote, "transcript_id": tid, "chunk_id": cid})

    for ch in chunks:
        raw = str(ch.get("text") or "")
        if len(raw) < 8:
            continue
        low_flat = " ".join(_norm_text(raw).split())
        padded = f" {low_flat} "

        for phrase, cat in _PHRASES:
            np = _norm_phrase(phrase)
            if len(np) < 4:
                continue
            if f" {np} " in padded:
                bump(phrase, cat, ch, _snippet(raw, np))

        toks = [t for t in _tokens(raw) if t not in _ALL_LEX_STOP]
        for tok in toks:
            if tok in brand_unigrams:
                bump(tok, "brand", ch, _snippet(raw, tok))
                continue
            lk = _lemma_key(tok)
            hit: LexCategory | None = None
            for cat in _CATEGORIES_ORDER:
                if cat == "brand":
                    continue
                seeds = _UNIGRAMS.get(cat, frozenset())
                if tok in seeds or lk in seeds:
                    hit = cat
                    break
            if hit is not None:
                bump(tok, hit, ch, _snippet(raw, tok))

    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in _CATEGORIES_ORDER}
    flat: list[dict[str, Any]] = []

    for _k, a in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
        cov = len(a["sources"])
        pct = round(100.0 * cov / ic, 1)
        row = {
            "term": a["term"],
            "category": a["category"],
            "count": int(a["count"]),
            "interview_coverage": cov,
            "pct": pct,
            "example_quotes": list(a["quotes"]),
        }
        by_cat[str(a["category"])].append(row)
        flat.append(row)

    for c in _CATEGORIES_ORDER:
        by_cat[c].sort(key=lambda r: (-int(r["count"]), str(r["term"])))
        by_cat[c] = by_cat[c][:top_per_category]

    flat.sort(key=lambda r: (-int(r["count"]), str(r["term"])))
    flat = flat[: top_per_category * len(_CATEGORIES_ORDER)]

    has_signals = sum(len(v) for v in by_cat.values()) > 0
    insufficient = "Недостаточно PR-сигналов в тексте для анализа лексики"

    return {
        "insufficient_message": insufficient,
        "has_signals": has_signals,
        "interview_count": ic,
        "categories_order": list(_CATEGORIES_ORDER),
        "by_category": by_cat,
        "signals_flat": flat,
    }
