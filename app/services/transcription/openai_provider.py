"""OpenAI Audio Transcriptions API (e.g. whisper-1, gpt-4o-mini-transcribe)."""

from __future__ import annotations

import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.infrastructure.settings import Settings
from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData

logger = logging.getLogger(__name__)


def _extension_for_mime(mime_type: str | None, filename_hint: str | None) -> str:
    if filename_hint and "." in filename_hint:
        return filename_hint.rsplit(".", 1)[-1].lower()[:8] or "bin"
    mt = (mime_type or "").lower()
    if "mpeg" in mt or mt.endswith("/mp3"):
        return "mp3"
    if "mp4" in mt or "m4a" in mt:
        return "m4a"
    if "wav" in mt:
        return "wav"
    if "webm" in mt:
        return "webm"
    if "ogg" in mt or "opus" in mt:
        return "ogg"
    if "flac" in mt:
        return "flac"
    return "bin"


def _parse_verbose_response(data: dict[str, Any], language_hint: str | None) -> StructuredTranscriptionResult:
    text = str(data.get("text") or "").strip()
    segments_out: list[TranscriptSegmentData] = []
    raw_segments = data.get("segments")
    if isinstance(raw_segments, list):
        for row in raw_segments:
            if not isinstance(row, dict):
                continue
            st = row.get("start")
            en = row.get("end")
            try:
                start_d = Decimal(str(float(st) if st is not None else 0.0))
            except (TypeError, ValueError):
                start_d = Decimal("0")
            try:
                end_d = Decimal(str(float(en) if en is not None else 0.0))
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
    if not segments_out and text:
        segments_out.append(
            TranscriptSegmentData(
                None,
                Decimal("0.000"),
                Decimal("1.000"),
                text,
                None,
            )
        )
    full_text = text or " ".join(s.text for s in segments_out)
    lang = data.get("language") if isinstance(data.get("language"), str) else language_hint
    return StructuredTranscriptionResult(
        full_text=full_text,
        language=lang,
        segments=segments_out,
        provider_name="openai",  # caller overwrites with openai:{model}
    )


class OpenAITranscriptionProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.openai_transcription_model
        timeout = float(settings.openai_transcription_timeout_seconds)
        key = (settings.openai_api_key or "").strip()
        self._client = AsyncOpenAI(api_key=key or None, timeout=timeout)

    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None,
        audio_file_path: Path | None,
        filename_hint: str | None,
    ) -> StructuredTranscriptionResult:
        if not (self._settings.openai_api_key or "").strip():
            raise ValueError(
                "OPENAI_API_KEY is required when RESEARCH_TRANSCRIPTION_PROVIDER=openai "
                "(no silent fallback to mock)"
            )
        ext = _extension_for_mime(mime_type, filename_hint)
        upload_name = filename_hint if filename_hint else f"audio.{ext}"
        buf = BytesIO(audio_bytes)
        buf.name = upload_name

        kwargs: dict[str, Any] = {
            "model": self._model,
            "file": buf,
        }
        if language_hint:
            kwargs["language"] = language_hint

        # whisper-1 supports verbose_json + segment timestamps; newer models may differ.
        use_verbose = self._model.startswith("whisper") or "transcribe" not in self._model.lower()
        if use_verbose:
            kwargs["response_format"] = "verbose_json"
            kwargs["timestamp_granularities"] = ["segment"]

        logger.info(
            "openai_transcription_request model=%s bytes=%s verbose_json=%s",
            self._model,
            len(audio_bytes),
            use_verbose,
        )
        try:
            raw = await self._client.audio.transcriptions.create(**kwargs)
        except APITimeoutError as e:
            logger.error(
                "OpenAI transcription timed out model=%s upload_name=%s",
                self._model,
                upload_name,
            )
            raise RuntimeError(f"OpenAI transcription timeout (model={self._model})") from e
        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            logger.error(
                "OpenAI transcription API error model=%s status=%s message=%s",
                self._model,
                getattr(e, "status_code", None),
                e,
            )
            raise RuntimeError(f"OpenAI transcription failed: {e}") from e

        if hasattr(raw, "model_dump"):
            data = raw.model_dump()
        elif isinstance(raw, dict):
            data = raw
        else:
            data = {"text": getattr(raw, "text", "") or ""}

        if not isinstance(data, dict):
            data = {"text": str(data)}

        label = f"openai:{self._model}"
        if use_verbose and isinstance(data.get("segments"), list):
            r = _parse_verbose_response(data, language_hint)
            return StructuredTranscriptionResult(
                full_text=r.full_text,
                language=r.language,
                segments=r.segments,
                provider_name=label,
            )

        text_only = str(data.get("text") or "").strip()
        if not text_only and hasattr(raw, "text"):
            text_only = str(getattr(raw, "text", "") or "").strip()
        if not text_only:
            raise RuntimeError("OpenAI transcription returned empty text")
        seg = TranscriptSegmentData(
            None,
            Decimal("0.000"),
            Decimal("1.000"),
            text_only,
            None,
        )
        return StructuredTranscriptionResult(
            full_text=text_only,
            language=language_hint,
            segments=[seg],
            provider_name=label,
        )
