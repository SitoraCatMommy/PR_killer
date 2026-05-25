from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import PaginationDep, ProjectServiceDep
from app.api.routes.research_batches import _dashboard_build_kwargs
from app.infrastructure.database import DbSession
from app.models.project import Project
from app.repositories.aggregation_snapshot_repository import AggregationSnapshotRepository
from app.repositories.research_batch_repository import ResearchBatchRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.schemas.common import ErrorResponse
from app.schemas.pagination import PaginatedMeta
from app.schemas.processing import ProcessingTaskQueued
from app.schemas.research_aggregation import (
    ResearchAggregationSnapshotRead,
    ResearchAggregationSnapshotResponse,
)
from app.schemas.research_batch import (
    BatchDashboardResponse,
    ResearchBatchCreate,
    ResearchBatchListResponse,
    ResearchBatchRead,
)
from app.schemas.research_project import ProjectCreate, ProjectListResponse, ProjectRead
from app.schemas.research_report import (
    PRAnalysisReadiness,
    ResearchReportEnvelope,
    ResearchReportRead,
)
from app.services.research_batch_dashboard_service import build_project_dashboard
from app.services.research_pipeline_orchestrator_service import ResearchPipelineOrchestratorService
from app.workers.tasks.research_aggregate import aggregate_project, generate_project_summary
from app.workers.tasks.research_report import prepare_and_generate_research_report

router = APIRouter(prefix="/projects", tags=["research-projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
async def create_project(body: ProjectCreate, svc: ProjectServiceDep) -> ProjectRead:
    try:
        return await svc.create(body)
    except ValueError as e:
        if str(e) == "invalid_name":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_name", "message": "Project name cannot be empty"},
            ) from e
        raise


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    svc: ProjectServiceDep,
    pagination: PaginationDep,
) -> ProjectListResponse:
    return await svc.list_paginated(
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.post(
    "/{project_id}/batches",
    response_model=ResearchBatchRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
)
async def create_project_batch(
    project_id: UUID,
    body: ResearchBatchCreate,
    session: DbSession,
) -> ResearchBatchRead:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = ResearchBatchRepository(session)
    batch = await repo.create(project_id=project_id, name=body.name, description=body.description)
    await session.commit()
    await session.refresh(batch)
    return ResearchBatchRead.model_validate(batch)


@router.get(
    "/{project_id}/batches",
    response_model=ResearchBatchListResponse,
    responses={404: {"model": ErrorResponse}},
)
async def list_project_batches(
    project_id: UUID,
    session: DbSession,
    pagination: PaginationDep,
) -> ResearchBatchListResponse:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = ResearchBatchRepository(session)
    rows, total = await repo.list_for_project(
        project_id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return ResearchBatchListResponse(
        items=[ResearchBatchRead.model_validate(r) for r in rows],
        meta=PaginatedMeta(total=total, limit=pagination.limit, offset=pagination.offset),
    )


@router.get(
    "/{project_id}/dashboard",
    response_model=BatchDashboardResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def get_project_dashboard(
    project_id: UUID,
    session: DbSession,
    group_by: str | None = Query(
        default=None,
        description="Optional segment field from source metadata_json (gender, age_range, segments, …).",
    ),
    segment_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    stopwords: bool = Query(default=False),
    compare_segment_a: str | None = Query(default=None),
    compare_segment_b: str | None = Query(default=None),
) -> BatchDashboardResponse:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    try:
        payload = await build_project_dashboard(session, project_id, **kwargs)
    except ValueError as e:
        if str(e) == "project_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "project_not_found", "message": "Project not found"},
            ) from e
        raise
    return BatchDashboardResponse.model_validate(payload)


@router.post(
    "/{project_id}/aggregate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_aggregate_project(
    project_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    task = aggregate_project.delay(str(project_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.post(
    "/{project_id}/summary/generate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_generate_project_summary(
    project_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    task = generate_project_summary.delay(str(project_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.get(
    "/{project_id}/aggregation",
    response_model=ResearchAggregationSnapshotResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_project_aggregation(
    project_id: UUID,
    session: DbSession,
) -> ResearchAggregationSnapshotResponse:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = AggregationSnapshotRepository(session)
    row = await repo.get_latest_research_entity_snapshot(project_id)
    if row is None:
        return ResearchAggregationSnapshotResponse(snapshot=None)
    return ResearchAggregationSnapshotResponse(
        snapshot=ResearchAggregationSnapshotRead(
            project_id=row.project_id,
            snapshot_type=row.snapshot_type,
            period_key=row.period_key,
            payload_json=dict(row.payload_json or {}),
            created_at=row.created_at,
        )
    )


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_project(project_id: UUID, svc: ProjectServiceDep) -> ProjectRead:
    row = await svc.get(project_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    return row


@router.get(
    "/{project_id}/report",
    response_model=ResearchReportEnvelope,
    responses={404: {"model": ErrorResponse}},
)
async def get_project_report(project_id: UUID, session: DbSession) -> ResearchReportEnvelope:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = ResearchReportRepository(session)
    row = await repo.get_latest_for_project(project_id)
    if row is None:
        return ResearchReportEnvelope(report=None)
    return ResearchReportEnvelope(report=ResearchReportRead.model_validate(row))


@router.get(
    "/{project_id}/pr-analysis/readiness",
    response_model=PRAnalysisReadiness,
    responses={404: {"model": ErrorResponse}},
)
async def get_project_pr_analysis_readiness(
    project_id: UUID,
    session: DbSession,
) -> PRAnalysisReadiness:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    # The sync readiness inspector only issues short SELECTs. Running it through the
    # sync facade keeps Celery and API readiness semantics aligned.
    service = ResearchPipelineOrchestratorService()
    readiness = await session.run_sync(
        lambda sync_session: service.inspect_project_pr_readiness_sync(sync_session, project_id)
    )
    return PRAnalysisReadiness.model_validate(readiness)


@router.post(
    "/{project_id}/report/generate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_generate_research_report(
    project_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    task = prepare_and_generate_research_report.delay(str(project_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.post(
    "/{project_id}/smart-report/generate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_smart_research_report(project_id: UUID, session: DbSession) -> ProcessingTaskQueued:
    """Продуктовый алиас: та же очередь Celery, внутри — smart synthesis + PR-отчёт."""
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    task = prepare_and_generate_research_report.delay(str(project_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.post(
    "/{project_id}/report/regenerate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_regenerate_research_report(
    project_id: UUID,
    session: DbSession,
) -> ProcessingTaskQueued:
    """Ставит в очередь новую генерацию, не удаляя предыдущий готовый отчёт заранее."""
    if await session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    task = prepare_and_generate_research_report.delay(str(project_id))
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_project(project_id: UUID, svc: ProjectServiceDep) -> Response:
    ok = await svc.delete(project_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
