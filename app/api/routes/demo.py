from fastapi import APIRouter, HTTPException, status

from app.api.deps import IngestionServiceDep, SettingsDep
from app.infrastructure.database import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.research_batch import DemoCreateResponse
from app.services.demo_batch_service import create_demo_batch

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post(
    "/create",
    response_model=DemoCreateResponse,
    responses={502: {"model": ErrorResponse}},
)
async def post_demo_create(
    session: DbSession,
    ingestion: IngestionServiceDep,
    settings: SettingsDep,
) -> DemoCreateResponse:
    try:
        return await create_demo_batch(session, ingestion, api_v1_prefix=settings.api_v1_prefix)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "demo_assets_missing", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "demo_create_failed", "message": str(e)},
        ) from e
