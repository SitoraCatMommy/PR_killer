"""Unified corpus scope for project-wide analytics and LLM synthesis."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.project_analysis_context import load_project_batch_view

CorpusView = SimpleNamespace


async def load_corpus_view(session: AsyncSession, project_id: UUID) -> CorpusView:
    """All project sources as a batch-compatible view for shared analytics services."""
    return await load_project_batch_view(session, project_id)
