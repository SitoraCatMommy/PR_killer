from __future__ import annotations

import logging
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.services.research_pipeline_orchestrator_service import ResearchPipelineOrchestratorService
from app.services.research_report_generation_service import ResearchReportGenerationService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.research_report.generate_research_report")
def generate_research_report(project_id: str) -> dict:
    """Generate report only (no auto chunk/extract/aggregate). Prefer ``prepare_and_generate_research_report``."""
    pid = UUID(project_id)
    svc = ResearchReportGenerationService()
    try:
        with sync_session_scope() as session:
            row = svc.generate_for_project_sync(session, pid)
    except ValueError as e:
        if str(e) == "project_not_found":
            logger.warning("generate_research_report: project missing %s", project_id)
            return {"status": "missing", "project_id": project_id}
        if str(e) == "openai_api_key_required_for_research_report":
            logger.error("generate_research_report: OPENAI_API_KEY not set for project %s", project_id)
            return {"status": "error", "code": "openai_required", "project_id": project_id}
        raise
    logger.info("generate_research_report: report_id=%s project_id=%s", row.id, project_id)
    return {"status": "ok", "project_id": project_id, "report_id": str(row.id)}


@celery_app.task(name="app.workers.tasks.research_report.prepare_and_generate_research_report")
def prepare_and_generate_research_report(project_id: str) -> dict:
    """Chunk/extract (gaps) + aggregate, then structured PR report."""
    pid = UUID(project_id)
    pipe = ResearchPipelineOrchestratorService()
    svc = ResearchReportGenerationService()
    try:
        with sync_session_scope() as session:
            pipe.ensure_project_ready_for_report_sync(session, pid)
        with sync_session_scope() as session:
            row = svc.generate_for_project_sync(session, pid)
    except ValueError as e:
        if str(e) == "project_not_found":
            logger.warning("prepare_and_generate_research_report: project missing %s", project_id)
            return {"status": "missing", "project_id": project_id}
        if str(e) == "openai_api_key_required_for_research_report":
            logger.error(
                "prepare_and_generate_research_report: OPENAI_API_KEY not set for project %s",
                project_id,
            )
            return {"status": "error", "code": "openai_required", "project_id": project_id}
        raise
    logger.info(
        "prepare_and_generate_research_report: report_id=%s project_id=%s",
        row.id,
        project_id,
    )
    return {"status": "ok", "project_id": project_id, "report_id": str(row.id)}
