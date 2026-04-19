from __future__ import annotations

from app.infrastructure.settings import Settings
from app.services.external_research.http_provider import HttpExternalResearchProvider
from app.services.external_research.mock_provider import MockExternalResearchProvider
from app.services.external_research.protocol import ExternalResearchProvider


def get_external_research_provider(settings: Settings) -> ExternalResearchProvider:
    p = settings.external_research_provider
    if p == "mock":
        return MockExternalResearchProvider()
    if p == "http":
        return HttpExternalResearchProvider(settings)
    raise ValueError(f"Unknown EXTERNAL_RESEARCH_PROVIDER: {p!r}")
