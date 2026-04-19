from app.schemas.common import ErrorResponse, HealthResponse, MessageResponse
from app.schemas.dashboard import DashboardAggregateRead
from app.schemas.insight import InsightCreate, InsightRead, InsightSourceLinkRead
from app.schemas.material import MaterialCreate, MaterialRead, MaterialUpdate

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "MessageResponse",
    "MaterialCreate",
    "MaterialRead",
    "MaterialUpdate",
    "InsightCreate",
    "InsightRead",
    "InsightSourceLinkRead",
    "DashboardAggregateRead",
]
