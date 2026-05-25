"""Load a project-wide source set as a batch-like view for shared analytics/LLM services."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument


async def load_project_batch_view(session: AsyncSession, project_id: UUID) -> SimpleNamespace:
    """Phantom batch: all project documents/audios as ``batch.sources`` for reuse of batch pipelines."""
    proj = await session.get(Project, project_id)
    if proj is None:
        raise ValueError("project_not_found")
    doc_ids = list(
        (await session.scalars(select(SourceDocument.id).where(SourceDocument.project_id == project_id))).all()
    )
    audio_ids = list(
        (await session.scalars(select(SourceAudio.id).where(SourceAudio.project_id == project_id))).all()
    )
    sources = [SimpleNamespace(source_document_id=d, source_audio_id=None) for d in doc_ids] + [
        SimpleNamespace(source_document_id=None, source_audio_id=a) for a in audio_ids
    ]
    return SimpleNamespace(
        id=project_id,
        project_id=project_id,
        name=getattr(proj, "name", "") or "Project",
        description=getattr(proj, "description", None),
        output_language=getattr(proj, "output_language", "ru"),
        single_file_multi_interview_mode=True,
        sources=sources,
    )
