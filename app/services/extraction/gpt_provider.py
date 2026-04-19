"""OpenAI Chat Completions–based research unit extraction (JSON)."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from app.domain.enums import EntityType
from app.domain.research_units import LEGACY_ENTITY_TYPES, PRIMARY_RESEARCH_ENTITY_TYPES
from app.infrastructure.settings import Settings, get_settings
from app.schemas.research_extraction import ExtractedEntityCandidate

logger = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 300
_MAX_ENTITIES_PER_CHUNK = 24

_ALLOWED = ", ".join(sorted(e.value for e in PRIMARY_RESEARCH_ENTITY_TYPES))

_SYSTEM = f"""Ты — аналитик пользовательских и продуктовых исследований. По фрагментам интервью или исследовательских материалов извлекай лаконичные **единицы анализа** (не списки сущностей в стиле NER: персоны, компании и т.п.).

Язык: поля title, content, evidence и любые подписи в tags — только на русском языке. Английский в этих полях запрещён (кроме непереводимых имён собственных из исходного текста). Значение entity_type — только из разрешённого списка латиницей.

Правила:
- Не копируй весь фрагмент дословно в content — переформулируй в короткие готовые для отчёта формулировки (не более 1–2 предложений).
- Каждая единица должна опираться на текст. В поле evidence помести короткую **дословную цитату** из фрагмента.
- Используй **только** такие значения entity_type: {_ALLOWED}
- Не используй person, organization, location, date, topic, claim, metric, reference, custom.
- confidence — число от 0.0 до 1.0.
- В tags можно добавить theme — короткая метка для группировки (по-русски).

Верни только JSON:
{{"entities":[{{"entity_type":"...","title":"краткая метка","content":"смысл","confidence":0.0,"tags":{{}},"evidence":"цитата"}}]}}"""


_LEGACY_MAP: dict[str, EntityType] = {
    "person": EntityType.SUPPORTING_FACT,
    "organization": EntityType.SUPPORTING_FACT,
    "location": EntityType.SUPPORTING_FACT,
    "date": EntityType.SUPPORTING_FACT,
    "topic": EntityType.BEHAVIOR_PATTERN,
    "claim": EntityType.SUPPORTING_FACT,
    "metric": EntityType.SUPPORTING_FACT,
    "reference": EntityType.SUPPORTING_FACT,
    "custom": EntityType.OPEN_QUESTION,
}


def _coerce_entity_type(raw: str) -> EntityType:
    s = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        et = EntityType(s)
        if et in PRIMARY_RESEARCH_ENTITY_TYPES:
            return et
        if s in _LEGACY_MAP:
            return _LEGACY_MAP[s]
        if et in LEGACY_ENTITY_TYPES:
            return EntityType.SUPPORTING_FACT
    except ValueError:
        pass
    return EntityType.SUPPORTING_FACT


class GPTExtractionProvider:
    """LLM extraction; returns [] on API/parse failure (service may apply fallbacks)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        key = (self._settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("openai_api_key_missing")
        self._model = self._settings.openai_extraction_model
        self._client = OpenAI(api_key=key, timeout=120.0)

    def _parse_entities_loose(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        raw_list = data.get("entities")
        if not isinstance(raw_list, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw_list:
            if isinstance(item, dict):
                out.append(item)
        return out

    def _to_candidate(
        self, chunk_text: str, item: dict[str, Any], chunk_index: int, slot: int
    ) -> ExtractedEntityCandidate | None:
        content = str(item.get("content", "") or "").strip()
        if not content:
            return None
        if len(content) > _MAX_CONTENT_LEN:
            logger.warning(
                "GPT extraction rejected entity chunk_index=%s slot=%s reason=content_too_long len=%s",
                chunk_index,
                slot,
                len(content),
            )
            return None
        ct = (chunk_text or "").strip()
        if ct and content == ct:
            logger.warning(
                "GPT extraction rejected entity chunk_index=%s slot=%s reason=content_equals_full_chunk",
                chunk_index,
                slot,
            )
            return None

        et = _coerce_entity_type(str(item.get("entity_type", "") or ""))
        title = str(item.get("title", "") or "").strip() or "Единица анализа"
        tags_raw = item.get("tags")
        tags = dict(tags_raw) if isinstance(tags_raw, dict) else {}
        tags.setdefault("provider", "gpt_extraction")
        ev_quote = str(item.get("evidence", "") or "").strip()
        try:
            conf = float(item.get("confidence", 0.75))
        except (TypeError, ValueError):
            conf = 0.75
        conf = max(0.0, min(1.0, conf))
        evidence_json: dict[str, Any] = {
            "quote": ev_quote[:2000] if ev_quote else content[:200],
            "provider": "gpt_extraction",
            "chunk_index": chunk_index,
        }
        try:
            return ExtractedEntityCandidate(
                entity_type=et,
                title=title[:512],
                content=content,
                confidence_score=conf,
                tags_json=tags,
                evidence_json=evidence_json,
            )
        except ValidationError as e:
            logger.warning("GPT extraction candidate validation failed slot=%s: %s", slot, e)
            return None

    def extract_from_chunk(
        self,
        *,
        text: str,
        chunk_index: int,
        source_filename: str | None,
    ) -> list[ExtractedEntityCandidate]:
        chunk_text = text or ""
        user = (
            f"Файл источника: {source_filename or '(не указан)'}\n"
            f"Индекс фрагмента: {chunk_index}\n\n"
            f"Текст:\n---\n{chunk_text}\n---\n\n"
            "Извлеки единицы анализа в формате JSON по системной инструкции. Все формулировки на русском."
        )
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except Exception:
            logger.exception("GPT extraction API error chunk_index=%s", chunk_index)
            return []

        raw_msg = completion.choices[0].message.content if completion.choices else None
        if not raw_msg:
            logger.warning("GPT extraction empty response chunk_index=%s", chunk_index)
            return []

        try:
            data: Any = json.loads(raw_msg)
        except json.JSONDecodeError as e:
            logger.warning("GPT extraction invalid JSON: %s", e)
            return []

        items = self._parse_entities_loose(data)
        if not items:
            return []

        out: list[ExtractedEntityCandidate] = []
        for slot, ent in enumerate(items[:_MAX_ENTITIES_PER_CHUNK], start=1):
            cand = self._to_candidate(chunk_text, ent, chunk_index, slot)
            if cand is not None:
                out.append(cand)
        return out
