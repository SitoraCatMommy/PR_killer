"""Google Gemini multimodal transcription (REST). No silent fallback — errors propagate."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import replace
from decimal import Decimal
from typing import Any

import httpx

from app.infrastructure.llm_http import httpx_timeout_for_upstream_read
from app.infrastructure.settings import Settings
from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData

logger = logging.getLogger(__name__)

# Multimodal endpoint: inline audio in `parts` + JSON response schema (supported for flash/pro families).
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _mime_for_audio(mime_type: str | None) -> str:
    mt = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
    if mt.startswith("audio/"):
        return mt
    return "audio/mpeg"


def _language_instruction(language_hint: str | None) -> str:
    if not language_hint:
        return (
            "Detect the spoken language (may be Uzbek, Russian, English, or mixed). "
            "Transcribe faithfully in the original script used in speech (e.g. Uzbek in Latin or Cyrillic as spoken)."
        )
    return f"The interview language is expected to be {language_hint!r}. Prioritize that language; still transcribe what is actually spoken."


def _build_user_prompt(language_hint: str | None) -> str:
    lang = _language_instruction(language_hint)
    return f"""You are a professional interview transcriber for PR / research intelligence.

{lang}

Return ONLY valid JSON (no markdown fences) with this exact shape:
{{
  "full_text": "complete transcript as one string",
  "detected_language": "ISO 639-1 code or uz for Uzbek",
  "segments": [
    {{"start_seconds": 0.0, "end_seconds": 12.5, "text": "segment text"}}
  ]
}}

Rules:
- ``full_text`` must be the full transcript (can mirror joined segments).
- ``segments``: time-ordered; use best-effort timestamps in seconds (float). If unsure, use coarse chunks.
- Do not translate; transcribe what was said.
- If audio is silent or unreadable, return full_text empty string and segments empty array.
"""


def _parse_gemini_json_payload(text: str) -> StructuredTranscriptionResult:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("gemini_transcription_invalid_json_root")
    full_text = str(data.get("full_text") or "").strip()
    detected = data.get("detected_language")
    detected_s = str(detected).strip().lower()[:12] if detected is not None else None
    segments_out: list[TranscriptSegmentData] = []
    segs = data.get("segments")
    if isinstance(segs, list):
        for row in segs:
            if not isinstance(row, dict):
                continue
            st = row.get("start_seconds", row.get("start"))
            en = row.get("end_seconds", row.get("end"))
            try:
                start_d = Decimal(str(float(st) if st is not None else 0.0))
            except (TypeError, ValueError):
                start_d = Decimal("0")
            try:
                end_d = Decimal(str(float(en) if en is not None else float(start_d) + 1.0))
            except (TypeError, ValueError):
                end_d = start_d + Decimal("1")
            seg_text = str(row.get("text") or "").strip()
            if not seg_text:
                continue
            segments_out.append(
                TranscriptSegmentData(
                    speaker_label=None,
                    start_seconds=start_d,
                    end_seconds=end_d,
                    text=seg_text,
                    confidence_score=None,
                )
            )
    if not segments_out and full_text:
        segments_out.append(
            TranscriptSegmentData(None, Decimal("0"), Decimal("1"), full_text, None),
        )
    if not full_text and segments_out:
        full_text = " ".join(s.text for s in segments_out)
    return StructuredTranscriptionResult(
        full_text=full_text,
        language=detected_s,
        segments=segments_out,
        provider_name="gemini",
    )


def _gemini_http_sync(
    *,
    settings: Settings,
    audio_bytes: bytes,
    mime_type: str | None,
    language_hint: str | None,
) -> StructuredTranscriptionResult:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is required when RESEARCH_TRANSCRIPTION_PROVIDER=gemini. "
            "Configure the key or choose another provider."
        )
    max_inline = min(int(settings.transcription_max_segment_bytes), 18 * 1024 * 1024)
    if len(audio_bytes) > max_inline:
        raise RuntimeError(
            f"gemini_transcription_payload_too_large: {len(audio_bytes)} bytes > {max_inline} "
            "(Gemini inline audio limit — use chunked ffmpeg pipeline / smaller TRANSCRIPTION_MAX_SEGMENT_BYTES)"
        )
    # Default aligned with Settings; avoid retired ids (e.g. gemini-2.0-flash).
    model = (settings.gemini_transcription_model or "gemini-2.5-flash").strip()
    url = f"{_GEMINI_URL.format(model=model)}?key={key}"
    mime = _mime_for_audio(mime_type)
    b64 = base64.standard_b64encode(audio_bytes).decode("ascii")
    body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": b64}},
                    {"text": _build_user_prompt(language_hint)},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.15,
            "responseMimeType": "application/json",
        },
    }
    read_budget = float(settings.gemini_transcription_timeout_seconds)
    timeout = httpx_timeout_for_upstream_read(read_seconds=read_budget, connect_seconds=60.0)
    logger.info(
        "gemini_transcription_request model=%s bytes=%s mime=%s language_hint=%s read_timeout_s=%s",
        model,
        len(audio_bytes),
        mime,
        language_hint,
        read_budget,
    )
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body)
    if resp.status_code >= 400:
        logger.error(
            "gemini_transcription_http_error status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:2000],
        )
        raise RuntimeError(
            f"gemini_transcription_http_error: HTTP {resp.status_code}: {(resp.text or '')[:500]}"
        )
    outer = resp.json()
    candidates = outer.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("gemini_transcription_empty_candidates")
    parts = (
        (candidates[0] or {}).get("content", {}).get("parts")
        if isinstance(candidates[0], dict)
        else None
    )
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("gemini_transcription_empty_parts")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("gemini_transcription_empty_text")
    result = _parse_gemini_json_payload(text)
    label = f"gemini:{model}"
    result = replace(
        result,
        language=result.language or language_hint,
        provider_name=label,
    )
    logger.info(
        "gemini_transcription_done model=%s provider_label=%s transcript_len=%s segment_count=%s detected_language=%s",
        model,
        result.provider_name,
        len(result.full_text or ""),
        len(result.segments),
        result.language,
    )
    return result


class GeminiTranscriptionProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None = None,
        audio_file_path: Any = None,
        filename_hint: str | None = None,
    ) -> StructuredTranscriptionResult:
        if not audio_bytes:
            raise RuntimeError("gemini_transcription_empty_audio_bytes")
        return await asyncio.to_thread(
            _gemini_http_sync,
            settings=self._settings,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            language_hint=language_hint,
        )
