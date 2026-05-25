"""Create a ready-made project + batch with bundled interview transcripts."""

from __future__ import annotations

import importlib.resources as pkg
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType

logger = logging.getLogger(__name__)
from app.repositories.project_public_report_repository import ProjectPublicReportRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.research_batch import DemoCreateResponse
from app.services.ingestion_service import IngestionService

_DEMO_FILES: tuple[tuple[str, dict[str, str]], ...] = (
    ("demo_interview_01.txt", {"gender": "female", "age_range": "25-34"}),
    ("demo_interview_02.txt", {"gender": "male", "age_range": "35-44"}),
    ("demo_interview_03.txt", {"gender": "female", "age_range": "45-54"}),
)


async def create_demo_batch(
    session: AsyncSession,
    ingestion: IngestionService,
    *,
    api_v1_prefix: str,
) -> DemoCreateResponse:
    projects = ProjectRepository(session)
    links = ProjectPublicReportRepository(session)

    project = await projects.create(
        name="Демо-проект",
        description="Автоматически создан для демонстрации и онбординга.",
        output_language="ru",
    )
    await session.flush()

    root = pkg.files("app.demo_data")
    for fname, meta in _DEMO_FILES:
        text = root.joinpath(fname).read_text(encoding="utf-8")
        await ingestion.upload_text_file(
            project.id,
            filename=fname,
            content=text.encode("utf-8"),
            mime_type="text/plain",
            source_type=SourceType.UPLOAD,
            extra_metadata=meta,
        )
        await session.flush()

    link = await links.upsert_for_project(project.id)
    await session.commit()

    try:
        from app.services.project_queue_service import schedule_project_processing

        schedule_project_processing(project.id)
    except Exception as exc:  # noqa: BLE001 — broker misconfig should not roll back demo data
        logger.exception("demo: failed to queue project processing: %s", exc)

    prefix = (api_v1_prefix or "/api/v1").rstrip("/")
    report_path = f"{prefix}/report/public/{link.token}"
    return DemoCreateResponse(
        batch_id=project.id,
        project_id=project.id,
        public_token=link.token,
        report_path=report_path,
    )
