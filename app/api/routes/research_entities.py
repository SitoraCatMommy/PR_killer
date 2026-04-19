from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import EntityQueryServiceDep, PaginationDep, ProjectServiceDep, SummaryQueryServiceDep
from app.domain.enums import EntityType
from app.schemas.common import ErrorResponse
from app.schemas.research_entity import EntityListResponse
from app.schemas.research_summary_schema import ResearchSummaryRead

router = APIRouter(prefix="/projects/{project_id}", tags=["research-entities"])


def _project_404():
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "project_not_found", "message": "Project not found"},
    )


@router.get(
    "/entities",
    response_model=EntityListResponse,
    responses={404: {"model": ErrorResponse}},
)
async def list_project_entities(
    project_id: UUID,
    svc: EntityQueryServiceDep,
    pagination: PaginationDep,
    entity_type: EntityType | None = Query(None),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    source_document_id: UUID | None = Query(None),
    source_audio_id: UUID | None = Query(None),
    transcript_id: UUID | None = Query(None),
    include_all_types: bool = Query(False, description="Include low-value types (e.g. supporting_fact)"),
) -> EntityListResponse:
    try:
        return await svc.list_for_project(
            project_id,
            entity_type=entity_type,
            min_confidence=min_confidence,
            source_document_id=source_document_id,
            source_audio_id=source_audio_id,
            transcript_id=transcript_id,
            offset=pagination.offset,
            limit=pagination.limit,
            include_all_types=include_all_types,
        )
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise


@router.get(
    "/summary",
    response_model=ResearchSummaryRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_project_summary(
    project_id: UUID,
    svc: SummaryQueryServiceDep,
    projects: ProjectServiceDep,
) -> ResearchSummaryRead:
    if await projects.get(project_id) is None:
        raise _project_404()
    try:
        row = await svc.get_latest_for_project(project_id)
    except ValueError as e:
        if str(e) == "project_not_found":
            raise _project_404() from e
        raise
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "summary_not_found", "message": "No research summary for this project yet"},
        )
    return row
