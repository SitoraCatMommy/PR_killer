"""External HTTP ASR endpoint (multipart upload, JSON response)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx

from app.infrastructure.settings import Settings
from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData


class HttpTranscriptionProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None,
        audio_file_path: Path | None,
        filename_hint: str | None,
    ) -> StructuredTranscriptionResult:
        if not self._settings.transcription_api_url:
            raise ValueError("TRANSCRIPTION_API_URL is required for RESEARCH_TRANSCRIPTION_PROVIDER=http")
        headers: dict[str, str] = {}
        if self._settings.transcription_api_key:
            headers["Authorization"] = f"Bearer {self._settings.transcription_api_key}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": (filename_hint or "audio", audio_bytes, mime_type or "application/octet-stream")}
            r = await client.post(
                str(self._settings.transcription_api_url),
                files=files,
                headers=headers,
            )
            r.raise_for_status()
            try:
                data = r.json()
            except Exception:
                data = None
        if not isinstance(data, dict):
            text = r.text
            seg = TranscriptSegmentData(
                None,
                Decimal("0.000"),
                Decimal("1.000"),
                text,
                None,
            )
            return StructuredTranscriptionResult(
                full_text=text,
                language=language_hint,
                segments=[seg],
                provider_name="http",
            )
        text = str(data.get("text") or "")
        segs_raw = data.get("segments")
        segments: list[TranscriptSegmentData] = []
        if isinstance(segs_raw, list):
            for i, row in enumerate(segs_raw):
                if not isinstance(row, dict):
                    continue
                segments.append(
                    TranscriptSegmentData(
                        speaker_label=row.get("speaker_label")
                        if isinstance(row.get("speaker_label"), str)
                        else None,
                        start_seconds=Decimal(str(row.get("start_seconds", i * 2))),
                        end_seconds=Decimal(str(row.get("end_seconds", i * 2 + 2))),
                        text=str(row.get("text") or ""),
                        confidence_score=row.get("confidence_score")
                        if isinstance(row.get("confidence_score"), (int, float))
                        else None,
                    )
                )
        if not segments and text:
            segments.append(
                TranscriptSegmentData(
                    None,
                    Decimal("0.000"),
                    Decimal("1.000"),
                    text,
                    None,
                )
            )
        full_text = text or " ".join(s.text for s in segments)
        lang = data.get("language") if isinstance(data.get("language"), str) else language_hint
        return StructuredTranscriptionResult(
            full_text=full_text,
            language=lang,
            segments=segments,
            provider_name="http",
        )
