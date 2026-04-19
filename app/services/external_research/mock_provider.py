from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MockExternalResearchProvider:
    """Deterministic placeholder articles (RU) for development."""

    def search_sync(
        self,
        *,
        themes: list[str],
        context: str,
        language: str = "ru",
    ) -> list[dict[str, Any]]:
        theme = themes[0] if themes else "исследование"
        logger.info("MockExternalResearchProvider themes=%s", themes[:5])
        return [
            {
                "title": "Доверие к цифровым финансовым сервисам: роль прозрачных коммуникаций",
                "url": "https://www.worldbank.org/en/topic/financialsector/brief/the-globe-findex-database",
                "relevance": f"Контекст доступа к деньгам и доверия к каналам — в связке с темой: {theme}.",
                "summary": "Обзор данных о финансовой инклюзии и значении понятных статусов операций.",
                "why_relevant_for_pr": "Даёт рамку для PR-нарратива о надёжности и контроле без «продуктовых обещаний».",
            },
            {
                "title": "Репутация финтех-компаний при обсуждении безопасности и мошенничества",
                "url": "https://www.ft.com/fintech",
                "relevance": "Материалы о том, как медиаполе читает инциденты и коммуникации финтех-брендов.",
                "summary": "Кейсы и повестка вокруг доверия, регуляторики и публичных ответов компаний.",
                "why_relevant_for_pr": "Полезно для оценки репутационных рисков и тона официальных комментариев.",
            },
        ]

