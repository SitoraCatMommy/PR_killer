from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.infrastructure.redis_client import get_redis, redis_ping
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
    )


@router.get("/health/ready")
async def readiness(settings: SettingsDep) -> dict[str, str | bool]:
    redis_ok = False
    try:
        client = await get_redis(settings)
        redis_ok = await redis_ping(client)
    except Exception:
        redis_ok = False
    return {
        "status": "ready" if redis_ok else "degraded",
        "redis": redis_ok,
    }
