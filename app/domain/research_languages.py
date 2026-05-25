"""Shared language codes for transcription hints and report output."""

from __future__ import annotations

from typing import Literal

TranscriptionLanguageOption = Literal["auto", "uz", "ru", "en"]
OutputLanguageOption = Literal["ru", "uz", "en"]

_VALID_TRANSCRIPTION = frozenset({"auto", "uz", "ru", "en"})
_VALID_OUTPUT = frozenset({"ru", "uz", "en"})


def normalize_transcription_language(raw: str | None) -> str | None:
    """Map UI/API value to storage: ``auto`` → ``None`` (provider auto-detect), else ISO-style code."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    v = raw.strip().lower()
    if v == "auto":
        return None
    if v in ("uz", "ru", "en"):
        return v
    return None


def normalize_output_language(raw: str | None, *, default: str = "ru") -> str:
    if raw is None or not str(raw).strip():
        return default
    v = str(raw).strip().lower()
    if v in _VALID_OUTPUT:
        return v
    return default


def parse_transcription_language_form(value: str | None) -> str | None:
    """Accept form field ``transcription_language`` (auto|uz|ru|en)."""
    if value is None or not str(value).strip():
        return None
    v = str(value).strip().lower()
    if v not in _VALID_TRANSCRIPTION:
        return None
    return normalize_transcription_language(v)


def resolve_transcription_upload(
    *,
    transcription_language: str | None = None,
    language: str | None = None,
) -> tuple[str | None, str]:
    """ASR hint for DB ``SourceAudio.language`` (None = auto) and UI label stored in metadata."""
    for raw in (transcription_language, language):
        if raw is None or not str(raw).strip():
            continue
        v = str(raw).strip().lower()
        if v == "auto":
            return (None, "auto")
        if v in ("uz", "ru", "en"):
            return (v, v)
    return (None, "auto")
