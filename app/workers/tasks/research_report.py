from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.services.research_pipeline_orchestrator_service import ResearchPipelineOrchestratorService
from app.services.research_report_generation_service import ResearchReportGenerationService

logger = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.research_report.generate_research_report"
)
def generate_research_report(project_id: str) -> dict[str, Any]:
    """Generate report only. Prefer ``prepare_and_generate_research_report``."""
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
            logger.error(
                "generate_research_report: OPENAI_API_KEY not set for project %s",
                project_id,
            )
            return {"status": "error", "code": "openai_required", "project_id": project_id}
        raise
    logger.info("generate_research_report: report_id=%s project_id=%s", row.id, project_id)
    return {"status": "ok", "project_id": project_id, "report_id": str(row.id)}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.research_report.prepare_and_generate_research_report"
)
def prepare_and_generate_research_report(project_id: str) -> dict[str, Any]:
    """Chunk/extract (gaps) + aggregate, then structured PR report."""
    pid = UUID(project_id)
    settings = get_settings()
    pipe = ResearchPipelineOrchestratorService(settings)
    svc = ResearchReportGenerationService(settings)
    report_id: UUID | None = None
    try:
        with sync_session_scope() as session:
            report = svc.create_generating_report_sync(session, pid, stage="preparing")
            report_id = report.id
        if report_id is None:
            raise RuntimeError("report_row_not_created")
        with sync_session_scope() as session:
            prep = pipe.prepare_project_for_pr_report_sync(
                session,
                pid,
                max_auto_extract_chunks=settings.pr_report_max_auto_extract_chunks,
                auto_prepare=settings.pr_report_auto_prepare,
            )
            if prep.get("blocked"):
                code = str(
                    (prep.get("blocking_reasons") or ["preparation_blocked"])[0]
                )
                svc.mark_report_failed_sync(
                    session,
                    report_id,
                    error_code=code,
                    error_message=(
                        "PR analysis preparation was blocked to avoid excessive token usage."
                    ),
                    extra={"prep": prep},
                )
                return {
                    "status": "blocked",
                    "code": code,
                    "project_id": project_id,
                    "report_id": str(report_id),
                }
            readiness = pipe.inspect_project_pr_readiness_sync(session, pid)
            if not readiness.get("ready_for_report"):
                code = str(
                    (readiness.get("blocking_reasons") or ["not_ready_for_report"])[0]
                )
                svc.mark_report_failed_sync(
                    session,
                    report_id,
                    error_code=code,
                    error_message="Not enough prepared PR signal to generate a useful report.",
                    extra={"prep": prep, "readiness": readiness},
                )
                return {
                    "status": "blocked",
                    "code": code,
                    "project_id": project_id,
                    "report_id": str(report_id),
                }
            svc.mark_report_stage_sync(
                session,
                report_id,
                stage="generating_report",
                extra={"prep": prep, "readiness": readiness},
            )
        with sync_session_scope() as session:
            row = svc.generate_for_project_sync(session, pid, report_id=report_id)
    except ValueError as e:
        if str(e) == "project_not_found":
            logger.warning("prepare_and_generate_research_report: project missing %s", project_id)
            return {"status": "missing", "project_id": project_id}
        if str(e) == "openai_api_key_required_for_research_report":
            logger.error(
                "prepare_and_generate_research_report: OPENAI_API_KEY not set for project %s",
                project_id,
            )
            if report_id is not None:
                with sync_session_scope() as session:
                    svc.mark_report_failed_sync(
                        session,
                        report_id,
                        error_code="openai_required",
                        error_message="OPENAI_API_KEY is required for PR report generation.",
                    )
            return {"status": "error", "code": "openai_required", "project_id": project_id}
        if report_id is not None:
            with sync_session_scope() as session:
                svc.mark_report_failed_sync(
                    session,
                    report_id,
                    error_code=str(e)[:120],
                    error_message=str(e),
                )
        raise
    except Exception as e:
        logger.exception("prepare_and_generate_research_report failed project_id=%s", project_id)
        if report_id is not None:
            with sync_session_scope() as session:
                svc.mark_report_failed_sync(
                    session,
                    report_id,
                    error_code="unexpected_error",
                    error_message=str(e) or type(e).__name__,
                )
        raise
    logger.info(
        "prepare_and_generate_research_report: report_id=%s project_id=%s",
        row.id,
        project_id,
    )
    return {"status": "ok", "project_id": project_id, "report_id": str(row.id)}
