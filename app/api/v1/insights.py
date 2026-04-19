from fastapi import APIRouter

from app.api.deps import InsightRepositoryDep
from app.schemas.insight import InsightRead

router = APIRouter()


@router.get("", response_model=list[InsightRead])
async def list_insights(repo: InsightRepositoryDep, limit: int = 100) -> list[InsightRead]:
    rows = await repo.list_with_links(limit=limit)
    return [InsightRead.model_validate(r) for r in rows]
