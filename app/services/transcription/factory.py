"""Resolve `TranscriptionProvider` from settings."""

from __future__ import annotations

from app.infrastructure.settings import Settings
from app.services.transcription.http_provider import HttpTranscriptionProvider
from app.services.transcription.mock_provider import MockTranscriptionProvider
from app.services.transcription.openai_provider import OpenAITranscriptionProvider
from app.services.transcription.protocol import TranscriptionProvider
from app.services.transcription.whisper_local_provider import WhisperLocalTranscriptionProvider


def get_transcription_provider(settings: Settings) -> TranscriptionProvider:
    p = settings.research_transcription_provider
    if p == "mock":
        return MockTranscriptionProvider()
    if p == "openai":
        return OpenAITranscriptionProvider(settings)
    if p == "whisper_local":
        return WhisperLocalTranscriptionProvider(settings)
    if p == "http":
        return HttpTranscriptionProvider(settings)
    raise ValueError(f"Unknown RESEARCH_TRANSCRIPTION_PROVIDER: {p!r}")
