"""Interactive Message Lab: score + rewrites + segment reactions (LLM, gated by strict PR readiness)."""

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
from app.schemas.research_batch import MessageLabAnalyzeRequest, MessageLabAnalyzeResponse, MessageLabSegmentReaction
from app.services.audience_portrait_service import build_portrait_context
from app.services.data_readiness_service import assess_strict_pr_readiness

logger = logging.getLogger(__name__)


def _system_prompt(lang: str) -> str:
    if lang == "uz":
        return (
            "Siz PR-matn tahlilchisisiz. Faqat berilgan intervyu iqtiboslari asosida baholang. "
            "JSON qaytaring: clarity_score, trust_score, risk_score (0..1), rewrite_variants (2 ta qator), "
            "segment_reactions: [{{segment, reaction}}]. Agar dalillar yetarli bo'lmasa, insufficient_evidence: true."
        )
    if lang == "en":
        return (
            "You are a PR copy analyst. Score the draft message using ONLY the provided interview quotes "
            "as ground truth. Return JSON: clarity_score, trust_score, risk_score (0..1), "
            "rewrite_variants (exactly 2 strings), segment_reactions array of {segment, reaction}. "
            "If fewer than 2 usable quotes, set insufficient_evidence: true and keep scores at 0."
        )
    return (
        "Ты PR-аналитик формулировок. Оцени черновик сообщения **только** по приложенным цитатам из интервью. "
        "Верни JSON: clarity_score, trust_score, risk_score (числа 0..1), rewrite_variants (ровно 2 строки), "
        "segment_reactions: массив {segment, reaction}. Если цитат меньше двух релевантных — insufficient_evidence: true, "
        "оценки обнули, не выдумывай реакции аудитории."
    )


def _parse_response(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


async def analyze_message_lab(
    session: AsyncSession,
    batch: ResearchBatch,
    body: MessageLabAnalyzeRequest,
    *,
    settings: Settings | None = None,
) -> MessageLabAnalyzeResponse:
    st = settings or get_settings()
    lang = (body.output_language or "ru").strip().lower()[:8]
    ctx = await build_portrait_context(session, batch, group_by=None, segment_value=None)
    strict = assess_strict_pr_readiness(ctx, output_language=lang)
    if not strict.ready:
        return MessageLabAnalyzeResponse(
            insufficient_evidence=True,
            notes=strict.user_message,
        )

    quotes = [q for q in (ctx.get("quotes") or []) if isinstance(q, dict)][:24]
    if len(quotes) < 2:
        return MessageLabAnalyzeResponse(
            insufficient_evidence=True,
            notes="Недостаточно цитат для проверки формулировки.",
        )

    payload = {
        "message": body.message.strip()[:4000],
        "quotes": quotes[:20],
        "segments_hint": list({str((q.get("type") or "")) for q in quotes})[:8],
        "required_output": {
            "insufficient_evidence": "boolean",
            "clarity_score": "number 0..1",
            "trust_score": "number 0..1",
            "risk_score": "number 0..1",
            "rewrite_variants": "array of exactly 2 strings",
            "segment_reactions": "array of {segment: string, reaction: string}",
            "notes": "string optional",
        },
    }
    user = json.dumps(payload, ensure_ascii=False)[:95_000]

    key = (st.openai_api_key or "").strip()
    if not key:
        raise ValueError("openai_api_key_missing")
    read_s = max(120.0, float(st.openai_http_timeout_seconds))
    client = OpenAI(api_key=key, timeout=httpx_timeout_for_upstream_read(read_seconds=read_s))

    def _call() -> dict[str, Any]:
        completion = client.chat.completions.create(
            model=st.openai_report_model,
            messages=[
                {"role": "system", "content": _system_prompt(lang)},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.25,
        )
        raw = completion.choices[0].message.content if completion.choices else None
        if not raw:
            raise ValueError("empty_llm_response")
        return _parse_response(raw)

    try:
        data = await asyncio.to_thread(_call)
    except Exception:
        logger.exception("message_lab LLM failed batch_id=%s", batch.id)
        raise

    if data.get("insufficient_evidence") is True:
        return MessageLabAnalyzeResponse(
            insufficient_evidence=True,
            notes=str(data.get("notes") or "insufficient evidence"),
        )

    def _f(name: str) -> float:
        try:
            return max(0.0, min(1.0, float(data.get(name) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    rewrites = data.get("rewrite_variants")
    rw: list[str] = []
    if isinstance(rewrites, list):
        rw = [str(x).strip() for x in rewrites if str(x).strip()][:2]
    segs_raw = data.get("segment_reactions")
    segs: list[MessageLabSegmentReaction] = []
    if isinstance(segs_raw, list):
        for it in segs_raw[:12]:
            if isinstance(it, dict):
                segs.append(
                    MessageLabSegmentReaction(
                        segment=str(it.get("segment") or "")[:120],
                        reaction=str(it.get("reaction") or "")[:600],
                    )
                )

    return MessageLabAnalyzeResponse(
        insufficient_evidence=False,
        clarity_score=_f("clarity_score"),
        trust_score=_f("trust_score"),
        risk_score=_f("risk_score"),
        rewrite_variants=rw,
        segment_reactions=segs,
        notes=str(data.get("notes") or "")[:800],
    )
