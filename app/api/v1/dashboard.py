from fastapi import APIRouter, status

from app.api.deps import DashboardRepositoryDep
from app.schemas.common import MessageResponse
from app.schemas.dashboard import DashboardAggregateRead

router = APIRouter()


@router.get("/aggregates", response_model=list[DashboardAggregateRead])
async def list_aggregates(repo: DashboardRepositoryDep) -> list[DashboardAggregateRead]:
    rows = await repo.list_all()
    return [DashboardAggregateRead.model_validate(r) for r in rows]


@router.post("/aggregates/recompute", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def recompute_aggregates() -> MessageResponse:
    from app.services.pipeline_dispatcher import MaterialPipelineDispatcher

    task_id = MaterialPipelineDispatcher.enqueue_dashboard_refresh()
    return MessageResponse(message=f"queued dashboard recompute {task_id}")
