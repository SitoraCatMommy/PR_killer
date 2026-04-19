"""Pluggable research summary generation (deterministic vs GPT)."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.settings import Settings, get_settings
from app.models.research_summary import ResearchSummary

logger = logging.getLogger(__name__)


@runtime_checkable
class ResearchSummaryProvider(Protocol):
    """Build and persist a `ResearchSummary` for a project."""

    def generate_project_summary_sync(self, session: Session, project_id: UUID) -> ResearchSummary:
        ...


def get_summary_provider(settings: Settings | None = None) -> ResearchSummaryProvider:
    settings = settings or get_settings()
    mode = settings.research_summary_provider
    has_openai = bool((settings.openai_api_key or "").strip())

    if mode == "gpt" and has_openai:
        from app.services.summary.gpt_summary_provider import GPTSummaryProvider

        logger.info("get_summary_provider: using GPTSummaryProvider")
        return GPTSummaryProvider(settings)

    if mode == "gpt" and not has_openai:
        logger.warning(
            "RESEARCH_SUMMARY_PROVIDER=gpt but OPENAI_API_KEY is missing; using deterministic SummaryService",
        )

    from app.services.research_summary_generation_service import SummaryService

    logger.info("get_summary_provider: using SummaryService (deterministic)")
    return SummaryService()
