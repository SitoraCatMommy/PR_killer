import logging
from typing import Protocol, runtime_checkable

from app.infrastructure.settings import Settings, get_settings
from app.schemas.research_extraction import ExtractedEntityCandidate
from app.services.extraction.mock_provider import MockResearchExtractionProvider

logger = logging.getLogger(__name__)


@runtime_checkable
class ResearchExtractionProvider(Protocol):
    """Pluggable extractor: chunk text → structured entity candidates."""

    def extract_from_chunk(
        self,
        *,
        text: str,
        chunk_index: int,
        source_filename: str | None,
    ) -> list[ExtractedEntityCandidate]:
        """Return zero or more validated candidates for this chunk."""
        ...


def get_extraction_provider(settings: Settings | None = None) -> ResearchExtractionProvider:
    settings = settings or get_settings()
    key = settings.research_extraction_provider
    has_openai = bool((settings.openai_api_key or "").strip())

    if key == "mock":
        provider = MockResearchExtractionProvider()
        logger.info(
            "get_extraction_provider: using MockResearchExtractionProvider (requested=%s)",
            key,
        )
        return provider

    if key == "gpt":
        if not has_openai:
            logger.error(
                "RESEARCH_EXTRACTION_PROVIDER=gpt but OPENAI_API_KEY is missing; falling back to mock",
            )
            return MockResearchExtractionProvider()
        from app.services.extraction.gpt_provider import GPTExtractionProvider

        provider = GPTExtractionProvider(settings)
        logger.info("get_extraction_provider: using GPTExtractionProvider")
        return provider

    raise ValueError(f"Unknown research_extraction_provider: {key}")
