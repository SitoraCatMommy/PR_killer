"""Create a ready-made project + batch with bundled interview transcripts."""

from __future__ import annotations

import importlib.resources as pkg
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import BatchSourceProcessingStatus, SourceType
from app.services.batch_queue_service import merge_batch_analysis_metadata

logger = logging.getLogger(__name__)
from app.repositories.batch_public_report_repository import BatchPublicReportRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.research_batch_repository import ResearchBatchRepository
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
    batches = ResearchBatchRepository(session)
    links = BatchPublicReportRepository(session)

    project = await projects.create(
        name="Демо-проект",
        description="Автоматически создан для демонстрации и онбординга.",
        output_language="ru",
    )
    await session.flush()
    batch = await batches.create(
        project_id=project.id,
        name="Демо: готовые интервью",
        description="Три подготовленных текстовых интервью с метаданными сегментов.",
    )
    await session.flush()

    root = pkg.files("app.demo_data")
    for i, (fname, meta) in enumerate(_DEMO_FILES):
        text = root.joinpath(fname).read_text(encoding="utf-8")
        doc = await ingestion.upload_text_file(
            project.id,
            filename=fname,
            content=text.encode("utf-8"),
            mime_type="text/plain",
            source_type=SourceType.UPLOAD,
            extra_metadata=meta,
        )
        row = await batches.add_document(
            batch.id,
            doc.id,
            sort_order=i,
            processing_status=BatchSourceProcessingStatus.PENDING.value,
        )
        doc.metadata_json = merge_batch_analysis_metadata(
            dict(doc.metadata_json or {}),
            batch_id=batch.id,
            batch_source_row_id=row.id,
            single_file_multi_interview_mode=batch.single_file_multi_interview_mode,
        )
        await session.flush()

    link = await links.upsert_for_batch(batch.id)
    await session.commit()

    try:
        from app.workers.tasks.batch_processing_queue import process_batch_processing_queue

        process_batch_processing_queue.delay(str(batch.id))
    except Exception as exc:  # noqa: BLE001 — broker misconfig should not roll back demo data
        logger.exception("demo: failed to queue batch processing: %s", exc)

    prefix = (api_v1_prefix or "/api/v1").rstrip("/")
    report_path = f"{prefix}/report/public/{link.token}"
    return DemoCreateResponse(
        batch_id=batch.id,
        project_id=project.id,
        public_token=link.token,
        report_path=report_path,
    )
