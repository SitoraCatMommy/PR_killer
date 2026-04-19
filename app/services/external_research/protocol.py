from __future__ import annotations

from typing import Any, Protocol


class ExternalResearchProvider(Protocol):
    """Pluggable web / literature discovery (sync for Celery)."""

    def search_sync(
        self,
        *,
        themes: list[str],
        context: str,
        language: str = "ru",
    ) -> list[dict[str, Any]]: ...
