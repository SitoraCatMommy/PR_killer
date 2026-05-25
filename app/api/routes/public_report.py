from fastapi import APIRouter, HTTPException, status

from app.infrastructure.database import DbSession
from app.repositories.batch_public_report_repository import BatchPublicReportRepository
from app.repositories.research_batch_repository import ResearchBatchRepository
from app.schemas.common import ErrorResponse
from app.schemas.research_batch import PublicReportResponse
from app.services.public_report_service import build_public_report_for_batch

router = APIRouter(prefix="/report", tags=["public-report"])


@router.get(
    "/public/{token}",
    response_model=PublicReportResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def get_public_report(token: str, session: DbSession) -> PublicReportResponse:
    raw = (token or "").strip()
    if not raw or len(raw) > 96:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Invalid or unknown link"},
        )
    link_repo = BatchPublicReportRepository(session)
    link = await link_repo.get_by_token(raw)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Invalid or unknown link"},
        )
    batch_repo = ResearchBatchRepository(session)
    batch = await batch_repo.get(link.batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Batch no longer exists"},
        )
    try:
        return await build_public_report_for_batch(session, batch, recalculate=False)
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required to build the public report",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "public_report_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "public_report_failed", "message": str(e)},
        ) from e
