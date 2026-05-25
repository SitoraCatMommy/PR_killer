from fastapi import APIRouter

from app.api.routes import (
    demo,
    project_analysis,
    public_report,
    research_batches,
    research_entities,
    research_projects,
    research_sources,
    research_transcripts,
)
from app.api.v1 import dashboard, health, insights, materials

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(research_projects.router)
api_router.include_router(research_batches.router)
api_router.include_router(project_analysis.router)
api_router.include_router(research_sources.router_nested)
api_router.include_router(research_sources.router_detail)
api_router.include_router(research_entities.router)
api_router.include_router(research_transcripts.router)
api_router.include_router(public_report.router)
api_router.include_router(demo.router)
api_router.include_router(materials.router, prefix="/materials", tags=["materials"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
