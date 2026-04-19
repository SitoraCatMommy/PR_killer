"""OpenAI-based synthesis of `ResearchSummary` from canonical entities."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import SummaryStatus
from app.infrastructure.settings import Settings, get_settings
from app.models.extracted_entity import ExtractedEntity
from app.models.project import Project
from app.models.research_summary import ResearchSummary
from app.services.research_summary_generation_service import SummaryService

logger = logging.getLogger(__name__)

_MAX_ENTITIES_IN_PROMPT = 150
_MAX_ENTITY_CONTENT_CHARS = 400

_SYSTEM = """Ты — аналитик исследований. По JSON с извлечёнными единицами ниже сформируй структурированную сводку.

Язык: summary_text, title и content во всех разделах — строго на русском языке, без английских слов и фраз (кроме UUID в supporting_entity_ids).

Правила:
- Не выдумывай факты; синтезируй только то, что разумно следует из единиц.
- summary_text — короткий связный абзац (не список счётчиков и не перечень типов).
- Элементы разделов: title, content (1–2 предложения), supporting_entity_ids (массив UUID строк — только из поля id входных единиц).
- Пустые разделы задавай пустыми массивами.

Верни только JSON с ключами: summary_text, key_findings, facts, hypotheses, risks, opportunities, recommendations, open_questions.
Каждое значение раздела — массив объектов с ключами title, content, supporting_entity_ids (массив строк)."""


def _compact_entities_for_prompt(entities: list[ExtractedEntity]) -> tuple[list[dict[str, Any]], set[UUID]]:
    """Return JSON-serializable rows and valid id set."""
    valid_ids: set[UUID] = set()
    rows: list[dict[str, Any]] = []
    for e in entities[:_MAX_ENTITIES_IN_PROMPT]:
        valid_ids.add(e.id)
        content = (e.content or "").strip()
        if len(content) > _MAX_ENTITY_CONTENT_CHARS:
            content = content[:_MAX_ENTITY_CONTENT_CHARS] + "…"
        rows.append(
            {
                "id": str(e.id),
                "entity_type": e.entity_type.value,
                "title": (e.title or "").strip(),
                "content": content,
                "confidence_score": e.confidence_score,
            }
        )
    return rows, valid_ids


def _normalize_section_items(raw: Any, valid_ids: set[UUID]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if not title and not content:
            continue
        sid_raw = item.get("supporting_entity_ids")
        ids: list[str] = []
        if isinstance(sid_raw, list):
            for s in sid_raw:
                try:
                    u = UUID(str(s).strip())
                    if u in valid_ids:
                        ids.append(str(u))
                except (ValueError, TypeError):
                    continue
        out.append(
            {
                "title": title[:512] if title else "Тезис",
                "content": content,
                "supporting_entity_ids": ids,
            }
        )
    return out


class GPTSummaryProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        key = (self._settings.openai_api_key or "").strip()
        if not key:
            raise ValueError("openai_api_key_missing")
        self._model = self._settings.openai_summary_model
        self._client = OpenAI(api_key=key, timeout=180.0)

    def _load_canonical_entities(self, session: Session, project_id: UUID) -> list[ExtractedEntity]:
        return list(
            session.scalars(
                select(ExtractedEntity)
                .where(
                    ExtractedEntity.project_id == project_id,
                    ExtractedEntity.canonical_entity_id.is_(None),
                )
                .order_by(ExtractedEntity.entity_type, ExtractedEntity.title, ExtractedEntity.id)
            ).all()
        )

    def _call_llm(self, payload_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        user = (
            "Единицы (JSON-массив):\n"
            + json.dumps(payload_rows, ensure_ascii=False)
            + "\n\nСформируй сводку в JSON по системной инструкции; весь текст на русском."
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
            logger.exception("GPT summary API error")
            return None
        raw = completion.choices[0].message.content if completion.choices else None
        if not raw:
            logger.warning("GPT summary empty response")
            return None
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("GPT summary invalid JSON: %s", e)
            return None
        return data if isinstance(data, dict) else None

    def generate_project_summary_sync(self, session: Session, project_id: UUID) -> ResearchSummary:
        if session.get(Project, project_id) is None:
            raise ValueError("project_not_found")

        canonicals = self._load_canonical_entities(session, project_id)
        payload_rows, valid_ids = _compact_entities_for_prompt(canonicals)

        if not payload_rows:
            logger.info("GPT summary: no canonical entities; using deterministic summary")
            return SummaryService().generate_project_summary_sync(session, project_id)

        data = self._call_llm(payload_rows)
        if data is None:
            logger.warning("GPT summary failed; falling back to deterministic SummaryService")
            return SummaryService().generate_project_summary_sync(session, project_id)

        summary_text = str(data.get("summary_text", "") or "").strip()
        if not summary_text:
            summary_text = "Сводка построена по извлечённым единицам."

        row = ResearchSummary(
            project_id=project_id,
            status=SummaryStatus.READY,
            summary_text=summary_text,
            key_findings_json=_normalize_section_items(data.get("key_findings"), valid_ids),
            facts_json=_normalize_section_items(data.get("facts"), valid_ids),
            hypotheses_json=_normalize_section_items(data.get("hypotheses"), valid_ids),
            risks_json=_normalize_section_items(data.get("risks"), valid_ids),
            opportunities_json=_normalize_section_items(data.get("opportunities"), valid_ids),
            recommendations_json=_normalize_section_items(data.get("recommendations"), valid_ids),
            open_questions_json=_normalize_section_items(data.get("open_questions"), valid_ids),
        )
        session.add(row)
        session.flush()
        return row
