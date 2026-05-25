from __future__ import annotations

import logging
from uuid import UUID

from app.domain.enums import ReportStatus
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.models.project import Project
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
    """Deprecated: batch-scoped reports removed — generate project-wide report instead."""
    del batch_id, output_language
    pid = UUID(project_id)
    svc = ResearchReportGenerationService()
    report_id: UUID | None = None
    try:
        with sync_session_scope() as session:
            if session.get(Project, pid) is None:
                raise ValueError("project_not_found")
            report_row = svc.create_generating_report_sync(session, pid)
            report_id = report_row.id

        with sync_session_scope() as session:
            row = svc.generate_for_project_sync(session, pid, report_id=report_id)
    except ValueError as e:
        code = str(e)
        if code == "project_not_found":
            logger.warning("generate_batch_research_report: project missing %s", project_id)
            return {"status": "missing", "project_id": project_id}
        if code == "openai_api_key_required_for_research_report":
            logger.error("generate_batch_research_report: OPENAI_API_KEY not set")
            return {"status": "error", "code": "openai_required"}
        _try_mark_report_failed(report_id)
        raise
    except Exception:
        _try_mark_report_failed(report_id)
        raise
    logger.info(
        "generate_batch_research_report: delegated to project report report_id=%s project_id=%s",
        row.id,
        project_id,
    )
    return {"status": "ok", "project_id": project_id, "report_id": str(row.id)}
