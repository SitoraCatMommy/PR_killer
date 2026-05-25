"""Split one long document into logical interview units (CustDev / PR analyst mode)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from uuid import UUID
from typing import Any

from app.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_MARKER_SPLIT = re.compile(
    r"(?m)(?:"
    r"^(?:Интервью|Interview|Сессия|Session)\s*[#№]?\s*\d+[^\n]*\s*$"
    r"|^Интервью\s*[-–—]\s*.+$"
    r"|^Респондент\s*[:：]\s*[^\n]+$"
    r"|^Respondent\s*[:：]\s*[^\n]+$"
    r"|^(?:Q|В)\s*[:：]\s*"
    r"|^A\s*[:：]\s*"
    r"|^SPEAKER\s*[\d#]+\s*[:#]"
    r"|^(?:Speaker|Interviewer|Moderator|Ведущий|Модератор)\s*[\d#]?\s*[:：#]"
    r"|^\[?(?:\d{1,2}:\d{2}(?::\d{2})?(?:\s*[-–]\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]?\s*$"
    r"|^#{1,3}\s*(?:Интервью|Interview|Session|Сессия)\b.*$"
    r"|^={3,}\s*.*$"
    r"|^---+\s*(?:\n|\s*$|(?:Интервью|Interview).*)"
    r"|^---+|\*{3,}\s*$"
    r")"
)

_SPEAKER_LINE = re.compile(
    r"(?m)^(?:Респондент|Respondent|Speaker|Интервьюер|Moderator)\s*[:：]\s*(.+)$",
)


@dataclass
class InterviewUnitDraft:
    unit_index: int
    speaker: str | None
    language: str | None
    language_confidence: float | None
    split_method: str
    raw_text: str
    metadata_json: dict[str, Any]


def _detect_language(text: str) -> tuple[str, float]:
    t = text or ""
    if not t.strip():
        return "unknown", 0.0
    cyr = len(re.findall(r"[А-Яа-яЁёЎўҚқҒғҲҳ]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    ogh = len(re.findall(r"[ʻʼ‘'`]", t))
    total = max(1, cyr + lat)
    ratio_c = cyr / total
    ratio_l = lat / total
    if ratio_c > 0.35 and ratio_l > 0.2:
        conf = min(0.9, 0.45 + abs(ratio_c - ratio_l))
        return "mixed", round(conf, 2)
    if ogh >= 3 and ratio_l > 0.25:
        return "uz", min(0.92, 0.55 + ogh / max(20, len(t) / 80))
    if ratio_c > 0.45:
        return "ru", min(0.95, 0.5 + ratio_c * 0.45)
    if ratio_l > 0.45:
        return "en", min(0.95, 0.5 + ratio_l * 0.45)
    return "mixed", 0.45


def _guess_speaker(block: str) -> str | None:
    m = _SPEAKER_LINE.search(block)
    if m:
        return m.group(1).strip()[:512] or None
    return None


def _split_by_markers(raw: str) -> list[str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    parts = [p.strip() for p in _MARKER_SPLIT.split(text) if (p or "").strip()]
    if len(parts) >= 2:
        return parts
    return None


def _split_by_numbered_headings(raw: str) -> list[str] | None:
    """Section headers like '### Interview 3' or '2. Респондент Иван' at line start."""
    text = (raw or "").strip()
    if not text or len(text) < 1_200:
        return None
    pattern = re.compile(
        r"(?m)(?:^#{1,3}\s*.+$|^(?:\d+[\).]\s+)(?:Интервью|Interview|Респондент|Session|Сегмент)\b.+$)"
    )
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    if len(parts) >= 2 and all(len(p) > 200 for p in parts[:3]):
        return parts
    return None


def _split_heuristic_blocks(raw: str, *, min_block: int = 900, max_block: int = 14_000) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paras:
        return [text]
    blocks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paras:
        ln = len(p)
        if buf_len + ln > max_block and buf:
            blocks.append("\n\n".join(buf))
            buf = [p]
            buf_len = ln
            continue
        buf.append(p)
        buf_len += ln + 2
        if buf_len >= min_block and len(buf) >= 2:
            blocks.append("\n\n".join(buf))
            buf = []
            buf_len = 0
    if buf:
        if blocks and len("\n\n".join(buf)) < min_block // 2:
            blocks[-1] = blocks[-1] + "\n\n" + "\n\n".join(buf)
        else:
            blocks.append("\n\n".join(buf))
    return [b for b in blocks if b.strip()]


def _llm_split_interviews(raw: str, settings: Settings) -> list[str] | None:
    key = (settings.openai_api_key or "").strip()
    if not key or len(raw) < 12_000:
        return None
    try:
        from openai import OpenAI

        from app.infrastructure.llm_http import httpx_timeout_for_upstream_read

        read_s = max(180.0, float(settings.openai_http_timeout_seconds))
        client = OpenAI(api_key=key, timeout=httpx_timeout_for_upstream_read(read_seconds=read_s))
        sample = raw[:24_000]
        completion = client.chat.completions.create(
            model=settings.openai_semantic_chunk_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You split a long file that may contain multiple customer interviews. "
                        "Return JSON {\"interviews\":[{\"text\":\"...\"}]} only. Each text is one interview, "
                        "preserve original language. Do not translate."
                    ),
                },
                {
                    "role": "user",
                    "content": "Split the following material into separate interviews:\n\n" + sample,
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        msg = completion.choices[0].message.content if completion.choices else None
        if not msg:
            return None
        data = json.loads(msg)
        arr = data.get("interviews")
        if not isinstance(arr, list) or len(arr) < 2:
            return None
        out: list[str] = []
        for it in arr:
            if isinstance(it, dict):
                t = str(it.get("text") or "").strip()
                if t:
                    out.append(t)
        return out if len(out) >= 2 else None
    except Exception:
        logger.info("llm_interview_split_failed", exc_info=True)
        return None


def build_interview_unit_drafts(
    raw: str,
    *,
    multi_interview_mode: bool,
    settings: Settings | None = None,
) -> list[InterviewUnitDraft]:
    """Produce ordered unit drafts. When ``multi_interview_mode`` is False, always one unit."""
    st = settings or get_settings()
    text = (raw or "").strip()
    if not text:
        return []

    if not multi_interview_mode:
        lang, conf = _detect_language(text)
        return [
            InterviewUnitDraft(
                unit_index=0,
                speaker=_guess_speaker(text),
                language=lang,
                language_confidence=conf,
                split_method="collapsed",
                raw_text=text,
                metadata_json={"mode": "single_unit", "split_mode": "auto_detect", "per_file": True},
            )
        ]

    parts = _split_by_markers(text)
    method = "marker"
    if not parts or len(parts) < 2:
        numbered = _split_by_numbered_headings(text)
        if numbered and len(numbered) >= 2:
            parts = numbered
            method = "numbered_heading"
    if not parts or len(parts) < 2:
        llm_parts = _llm_split_interviews(text, st)
        if llm_parts:
            parts = llm_parts
            method = "llm"
        else:
            parts = _split_heuristic_blocks(text)
            method = "heuristic"

    if len(parts) < 2:
        lang, conf = _detect_language(text)
        return [
            InterviewUnitDraft(
                unit_index=0,
                speaker=_guess_speaker(text),
                language=lang,
                language_confidence=conf,
                split_method="single",
                raw_text=text,
                metadata_json={
                    "reason": "no_confident_multi_split",
                    "split_mode": "auto_detect",
                },
            )
        ]

    drafts: list[InterviewUnitDraft] = []
    for i, block in enumerate(parts):
        b = block.strip()
        if not b:
            continue
        lang, conf = _detect_language(b)
        drafts.append(
            InterviewUnitDraft(
                unit_index=len(drafts),
                speaker=_guess_speaker(b),
                language=lang,
                language_confidence=conf,
                split_method=method,
                raw_text=b,
                metadata_json={
                    "marker_rank": i,
                    "unit_index": len(drafts),
                    "split_mode": "auto_detect",
                },
            )
        )
    return drafts


def drafts_to_rows(
    drafts: list[InterviewUnitDraft],
    *,
    project_id: UUID,
    source_document_id: UUID,
) -> list[dict[str, Any]]:
    return [
        {
            "project_id": project_id,
            "source_document_id": source_document_id,
            "unit_index": d.unit_index,
            "speaker": d.speaker,
            "language": d.language,
            "language_confidence": d.language_confidence,
            "split_method": d.split_method,
            "raw_text": d.raw_text,
            "metadata_json": dict(d.metadata_json),
        }
        for d in drafts
    ]
