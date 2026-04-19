from functools import lru_cache
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.infrastructure.settings import Settings, get_settings


@lru_cache
def _redis_client(url: str) -> Redis:
    return aioredis.from_url(url, decode_responses=True)


async def get_redis(settings: Settings | None = None) -> Redis:
    s = settings or get_settings()
    return _redis_client(str(s.redis_url))


async def redis_ping(client: Redis) -> bool:
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def redis_set_json(client: Redis, key: str, value: Any, ttl_seconds: int | None = None) -> None:
    import json

    payload = json.dumps(value)
    if ttl_seconds is not None:
        await client.setex(key, ttl_seconds, payload)
    else:
        await client.set(key, payload)
