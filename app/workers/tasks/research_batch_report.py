from __future__ import annotations

import logging
from uuid import UUID

from app.domain.enums import ReportStatus
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.models.project import Project
from app.models.research_batch import ResearchBatch
from app.models.research_report import ResearchReport
from app.services.research_report_generation_service import ResearchReportGenerationService

logger = logging.getLogger(__name__)


def _try_mark_report_failed(report_id: UUID | None) -> None:
    if report_id is None:
        return
    try:
        with sync_session_scope() as session:
            rep = session.get(ResearchReport, report_id)
            if rep is not None:
                rep.status = ReportStatus.FAILED
    except Exception:
        logger.exception("Failed to mark report %s as FAILED", report_id)


@celery_app.task(name="app.workers.tasks.research_batch_report.generate_batch_research_report")
def generate_batch_research_report(project_id: str, batch_id: str, output_language: str | None = None) -> dict:
    pid = UUID(project_id)
    bid = UUID(batch_id)
    svc = ResearchReportGenerationService()
    report_id: UUID | None = None
    try:
        with sync_session_scope() as session:
            proj = session.get(Project, pid)
            if proj is None:
                raise ValueError("project_not_found")
            batch = session.get(ResearchBatch, bid)
            if batch is None or batch.project_id != pid:
                raise ValueError("batch_not_found")
            if output_language and output_language.strip().lower() in ("ru", "uz", "en"):
                batch.output_language = output_language.strip().lower()
                session.flush()
            report_id = svc.initialize_report_sync(session, pid, batch_id=bid)

        with sync_session_scope() as session:
            row = svc.generate_for_project_sync(session, pid, batch_id=bid, pre_created_report_id=report_id)
    except ValueError as e:
        code = str(e)
        if code == "project_not_found":
            logger.warning("generate_batch_research_report: project missing %s", project_id)
            return {"status": "missing", "project_id": project_id}
        if code == "batch_not_found":
            logger.warning("generate_batch_research_report: batch missing %s", batch_id)
            return {"status": "error", "code": "batch_not_found", "batch_id": batch_id}
        if code == "batch_has_no_sources":
            _try_mark_report_failed(report_id)
            return {"status": "error", "code": "batch_has_no_sources", "batch_id": batch_id}
        if code == "openai_api_key_required_for_research_report":
            logger.error("generate_batch_research_report: OPENAI_API_KEY not set")
            return {"status": "error", "code": "openai_required"}
        _try_mark_report_failed(report_id)
        raise
    except Exception:
        _try_mark_report_failed(report_id)
        raise
    logger.info(
        "generate_batch_research_report: report_id=%s project_id=%s batch_id=%s",
        row.id,
        project_id,
        batch_id,
    )
    return {"status": "ok", "project_id": project_id, "batch_id": batch_id, "report_id": str(row.id)}
