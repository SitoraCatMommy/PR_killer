"""Transcription provider interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.services.transcription.data import StructuredTranscriptionResult


class TranscriptionProvider(Protocol):
    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None,
        audio_file_path: Path | None,
        filename_hint: str | None,
    ) -> StructuredTranscriptionResult: ...
