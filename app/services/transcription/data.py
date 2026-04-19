"""Shared transcription result types (used by providers and TranscriptionService)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TranscriptSegmentData:
    speaker_label: str | None
    start_seconds: Decimal
    end_seconds: Decimal
    text: str
    confidence_score: float | None = None


@dataclass(frozen=True)
class StructuredTranscriptionResult:
    full_text: str
    language: str | None
    segments: list[TranscriptSegmentData]
    provider_name: str
