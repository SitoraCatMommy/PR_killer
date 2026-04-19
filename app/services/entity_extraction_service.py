import re
from typing import Any

from app.domain.enums import EntityKind


class EntityExtractionService:
    """Deterministic placeholder extraction; swap for NER/LLM pipelines in production."""

    _email = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    _url = re.compile(r"https?://[^\s)]+")
    _heading = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)

    def extract(self, normalized_text: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for m in self._email.finditer(normalized_text):
            entities.append(
                {
                    "kind": EntityKind.CUSTOM.value,
                    "label": m.group(0),
                    "normalized_value": m.group(0).lower(),
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "payload": {"pattern": "email"},
                }
            )
        for m in self._url.finditer(normalized_text):
            entities.append(
                {
                    "kind": EntityKind.TOPIC.value,
                    "label": m.group(0),
                    "normalized_value": m.group(0),
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "payload": {"pattern": "url"},
                }
            )
        for m in self._heading.finditer(normalized_text):
            line = m.group(1).strip()
            entities.append(
                {
                    "kind": EntityKind.TOPIC.value,
                    "label": line[:512],
                    "normalized_value": line.lower()[:1024],
                    "span_start": m.start(),
                    "span_end": m.end(),
                    "payload": {"pattern": "heading"},
                }
            )
        return entities
