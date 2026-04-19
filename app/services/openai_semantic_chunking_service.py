"""Split long text into semantic segments via OpenAI Chat Completions (JSON)."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from app.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_SYSTEM = """Ты разбиваешь исследовательский текст на смысловые непрерывные фрагменты для последующего анализа.

Правила:
- Сохраняй язык и формулировки исходника; не переводи и не перефразируй. Не добавляй английский и другой текст, которого нет во входе.
- Каждый фрагмент — одна связная единица (тема, аргумент, эпизод, блок инструкции).
- Порядок фрагментов совпадает с исходным текстом.
- По возможности длина фрагмента примерно 150–4000 символов; слишком мелкие части объединяй с соседними.
- Склейка всех text подряд (без добавления символов между ними) должна в точности восстановить входной текст.

Верни только JSON вида {"segments":[{"text":"..."},...]} — имена ключей segments и text оставь латиницей (требование парсера); внутри text только фрагменты исходника."""


class _SegmentModel(BaseModel):
    text: str = Field(min_length=1)


class _SegmentsResponse(BaseModel):
    segments: list[_SegmentModel] = Field(default_factory=list)


class OpenAISemanticChunkingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        key = (self._settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("openai_api_key_missing")
        self._model = self._settings.openai_semantic_chunk_model
        self._window = self._settings.openai_semantic_chunk_window_chars
        self._client = OpenAI(api_key=key, timeout=120.0)

    def _windows(self, text: str) -> list[str]:
        if len(text) <= self._window:
            return [text]
        return [text[i : i + self._window] for i in range(0, len(text), self._window)]

    def _parse_segments(self, content: str) -> list[str]:
        try:
            data: Any = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"openai_semantic_invalid_json: {e}") from e
        try:
            parsed = _SegmentsResponse.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"openai_semantic_invalid_shape: {e}") from e
        return [s.text.strip() for s in parsed.segments if s.text.strip()]

    def _split_window(self, window_text: str) -> list[str]:
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": window_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = completion.choices[0].message.content
        if not raw:
            raise ValueError("openai_semantic_empty_response")
        segments = self._parse_segments(raw)
        if not segments:
            raise ValueError("openai_semantic_no_segments")
        joined = "".join(segments)
        if joined != window_text:
            norm_j = "".join(joined.split())
            norm_w = "".join(window_text.split())
            if norm_j != norm_w:
                logger.warning(
                    "Semantic segments do not exactly match window (len window=%s len joined=%s); using segments as returned",
                    len(window_text),
                    len(joined),
                )
        return segments

    def chunk_full_text(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        all_parts: list[str] = []
        for win in self._windows(text):
            all_parts.extend(self._split_window(win))
        return all_parts
