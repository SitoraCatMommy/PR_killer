from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.infrastructure.settings import Settings
from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData
from app.services.transcription.factory import get_transcription_provider
from app.services.transcription.mock_provider import MockTranscriptionProvider

logger = logging.getLogger(__name__)

__all__ = [
    "TranscriptSegmentData",
    "StructuredTranscriptionResult",
    "TranscriptionService",
]


class TranscriptionService:
    """ASR facade: delegates to `TranscriptionProvider` from `RESEARCH_TRANSCRIPTION_PROVIDER`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None = None,
        audio_file_path: Path | None = None,
        filename_hint: str | None = None,
    ) -> StructuredTranscriptionResult:
        prov_name = self._settings.research_transcription_provider
        openai_key_present: bool | None = (
            bool((self._settings.openai_api_key or "").strip()) if prov_name == "openai" else None
        )
        model_log = (
            self._settings.openai_transcription_model
            if prov_name == "openai"
            else (self._settings.whisper_local_model if prov_name == "whisper_local" else "-")
        )
        path_str = str(audio_file_path) if audio_file_path else "(bytes only)"
        logger.info(
            "transcription_start provider=%s openai_key_present=%s audio_path=%s model=%s",
            prov_name,
            openai_key_present,
            path_str,
            model_log,
        )

        provider = get_transcription_provider(self._settings)
        try:
            result = await provider.transcribe_structured(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                language_hint=language_hint,
                audio_file_path=audio_file_path,
                filename_hint=filename_hint,
            )
        except Exception:
            logger.exception("transcription_failed provider=%s", prov_name)
            if self._settings.research_transcription_fallback_to_mock and prov_name != "mock":
                logger.error(
                    "transcription_fallback: RESEARCH_TRANSCRIPTION_FALLBACK_TO_MOCK=true; "
                    "returning mock transcript after error"
                )
                result = await MockTranscriptionProvider().transcribe_structured(
                    audio_bytes=audio_bytes,
                    mime_type=mime_type,
                    language_hint=language_hint,
                    audio_file_path=audio_file_path,
                    filename_hint=filename_hint,
                )
            else:
                raise

        logger.info(
            "transcription_done configured_provider=%s result_provider=%s transcript_len=%s segment_count=%s",
            prov_name,
            result.provider_name,
            len(result.full_text or ""),
            len(result.segments),
        )
        return result

    def transcribe_structured_sync(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None = None,
        audio_file_path: Path | None = None,
        filename_hint: str | None = None,
    ) -> StructuredTranscriptionResult:
        return asyncio.run(
            self.transcribe_structured(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                language_hint=language_hint,
                audio_file_path=audio_file_path,
                filename_hint=filename_hint,
            )
        )

    async def transcribe(self, *, audio_bytes: bytes, mime_type: str | None) -> str:
        r = await self.transcribe_structured(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            language_hint=None,
            audio_file_path=None,
            filename_hint=None,
        )
        return r.full_text

    def transcribe_sync(self, *, audio_bytes: bytes, mime_type: str | None) -> str:
        return self.transcribe_structured_sync(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            filename_hint=None,
        ).full_text
