from typing import Annotated

from fastapi import Depends, Query

from app.infrastructure.database import DbSession
from app.infrastructure.settings import Settings, get_settings
from app.infrastructure.storage.local import LocalFileStorage
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.material_repository import MaterialRepository
from app.schemas.pagination import PaginationParams
from app.services.entity_query_service import EntityQueryService
from app.services.ingestion_service import IngestionService
from app.services.material_service import MaterialService
from app.services.project_service import ProjectService
from app.services.source_query_service import SourceQueryService
from app.services.summary_query_service import SummaryQueryService


def pagination_params(
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset"),
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]


def get_local_storage(settings: Annotated[Settings, Depends(get_settings)]) -> LocalFileStorage:
    return LocalFileStorage(settings)


LocalStorageDep = Annotated[LocalFileStorage, Depends(get_local_storage)]


def get_project_service(session: DbSession) -> ProjectService:
    return ProjectService(session)


def get_source_query_service(session: DbSession) -> SourceQueryService:
    return SourceQueryService(session)


def get_entity_query_service(session: DbSession) -> EntityQueryService:
    return EntityQueryService(session)


def get_summary_query_service(session: DbSession) -> SummaryQueryService:
    return SummaryQueryService(session)


def get_ingestion_service(session: DbSession, storage: LocalStorageDep) -> IngestionService:
    return IngestionService(session, storage)


def get_material_service(session: DbSession) -> MaterialService:
    return MaterialService(session)


def get_material_repository(session: DbSession) -> MaterialRepository:
    return MaterialRepository(session)


def get_dashboard_repository(session: DbSession) -> DashboardRepository:
    return DashboardRepository(session)


def get_insight_repository(session: DbSession) -> InsightRepository:
    return InsightRepository(session)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
SourceQueryServiceDep = Annotated[SourceQueryService, Depends(get_source_query_service)]
EntityQueryServiceDep = Annotated[EntityQueryService, Depends(get_entity_query_service)]
SummaryQueryServiceDep = Annotated[SummaryQueryService, Depends(get_summary_query_service)]
IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
MaterialServiceDep = Annotated[MaterialService, Depends(get_material_service)]
DashboardRepositoryDep = Annotated[DashboardRepository, Depends(get_dashboard_repository)]
InsightRepositoryDep = Annotated[InsightRepository, Depends(get_insight_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
