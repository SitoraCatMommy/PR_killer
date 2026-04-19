from __future__ import annotations

import logging
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db_sync import sync_session_scope
from app.infrastructure.settings import get_settings
from app.services.research_pipeline_orchestrator_service import ResearchPipelineOrchestratorService
from app.services.research_project_aggregation_service import ResearchAggregationService
from app.services.summary.provider import get_summary_provider

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.research_aggregate.aggregate_project")
def aggregate_project(project_id: str) -> dict:
    pid = UUID(project_id)
    svc = ResearchAggregationService()
    with sync_session_scope() as session:
        payload = svc.aggregate_project_sync(session, pid)
    totals = payload.get("totals") or {}
    logger.info(
        "Aggregated project %s canonical_entities=%s total_entity_rows=%s snapshot_keys=%s",
        project_id,
        totals.get("canonical_entities"),
        totals.get("total_entity_rows"),
        list(payload.keys()),
    )
    return {"status": "ok", "project_id": project_id, "totals": payload.get("totals", {})}


@celery_app.task(name="app.workers.tasks.research_aggregate.generate_project_summary")
def generate_project_summary(project_id: str) -> dict:
    pid = UUID(project_id)
    settings = get_settings()
    summary_svc = get_summary_provider(settings)
    logger.info(
        "generate_project_summary: provider_class=%s research_summary_provider=%s",
        type(summary_svc).__qualname__,
        settings.research_summary_provider,
    )
    with sync_session_scope() as session:
        try:
            ResearchPipelineOrchestratorService().ensure_project_sources_pipeline_sync(session, pid)
            ResearchAggregationService().aggregate_project_sync(session, pid)
            row = summary_svc.generate_project_summary_sync(session, pid)
        except ValueError as e:
            if str(e) == "project_not_found":
                logger.warning("generate_project_summary: missing project %s", project_id)
                return {"status": "missing", "project_id": project_id}
            raise
    return {"status": "ok", "project_id": project_id, "summary_id": str(row.id)}
