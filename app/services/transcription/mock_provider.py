"""Deterministic placeholder ASR for local development and tests."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData


class MockTranscriptionProvider:
    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None,
        audio_file_path: Path | None,
        filename_hint: str | None,
    ) -> StructuredTranscriptionResult:
        lang = language_hint or "en"
        uid = uuid.uuid4().hex[:8]
        path_note = f", path {audio_file_path}" if audio_file_path else ""
        fn = filename_hint or "(no filename)"
        s1 = TranscriptSegmentData(
            speaker_label="SPEAKER_1",
            start_seconds=Decimal("0.000"),
            end_seconds=Decimal("4.250"),
            text=(
                f"[mock transcript {uid}] Opening segment. "
                f"Audio size {len(audio_bytes)} bytes, mime {mime_type or 'unknown'}, file {fn}{path_note}."
            ),
            confidence_score=0.92,
        )
        s2 = TranscriptSegmentData(
            speaker_label="SPEAKER_2",
            start_seconds=Decimal("4.250"),
            end_seconds=Decimal("9.800"),
            text="[mock transcript] Follow-up segment with structured ASR placeholder.",
            confidence_score=0.88,
        )
        full_text = f"{s1.text} {s2.text}"
        return StructuredTranscriptionResult(
            full_text=full_text,
            language=lang,
            segments=[s1, s2],
            provider_name="mock",
        )
