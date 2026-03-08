"""Thin async Redis cache layer with JSON serialisation and TTL fallback."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def cache_get(key: str) -> Any | None:
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        logger.warning("Redis GET failed for key=%s, falling back to None", key, exc_info=True)
    return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl or settings.CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("Redis SET failed for key=%s", key, exc_info=True)


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception:
        logger.warning("Redis DELETE failed for key=%s", key, exc_info=True)
