from __future__ import annotations

import logging
from typing import Any

import httpx

from app.infrastructure.settings import Settings

logger = logging.getLogger(__name__)


class HttpExternalResearchProvider:
    """POST JSON to configured endpoint; expects { \"articles\": [ {...}, ... ] }."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search_sync(
        self,
        *,
        themes: list[str],
        context: str,
        language: str = "ru",
    ) -> list[dict[str, Any]]:
        url = self._settings.external_research_api_url
        if not url:
            raise ValueError("EXTERNAL_RESEARCH_API_URL is required for EXTERNAL_RESEARCH_PROVIDER=http")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        key = (self._settings.external_research_api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "themes": themes,
            "context": context,
            "language": language,
        }
        with httpx.Client(timeout=float(self._settings.external_research_timeout_seconds)) as client:
            r = client.post(str(url), json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        articles = data.get("articles") if isinstance(data, dict) else None
        if not isinstance(articles, list):
            logger.warning("HttpExternalResearchProvider: missing articles[] in response")
            return []
        out: list[dict[str, Any]] = []
        for row in articles:
            if isinstance(row, dict) and row.get("title"):
                out.append(
                    {
                        "title": str(row.get("title", "")),
                        "url": str(row.get("url", "")),
                        "relevance": str(row.get("relevance", "")),
                        "summary": str(row.get("summary", "")),
                    }
                )
        return out
