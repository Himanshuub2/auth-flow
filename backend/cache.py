"""Thin async Redis cache layer with JSON serialisation and TTL fallback."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.Redis | None = None
_redis_unavailable = False


async def get_redis() -> aioredis.Redis:
    global _pool, _redis_unavailable
    if _redis_unavailable:
        raise RuntimeError("Redis disabled for current process")
    if _pool is None:
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


def _disable_redis(exc: Exception) -> None:
    global _redis_unavailable, _pool
    if not _redis_unavailable:
        logger.warning(
            "Redis unavailable at %s; cache disabled for this process",
            settings.REDIS_URL,
        )
    _redis_unavailable = True
    _pool = None


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def cache_get(key: str) -> Any | None:
    if not settings.REDIS_URL:
        return None
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception as exc:
        _disable_redis(exc)
        logger.warning("Redis GET failed for key=%s, falling back to None", key)
    return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    if not settings.REDIS_URL:
        return
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl or settings.CACHE_TTL_SECONDS)
    except Exception as exc:
        _disable_redis(exc)
        logger.warning("Redis SET failed for key=%s", key)


async def cache_delete(key: str) -> None:
    if not settings.REDIS_URL:
        return
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as exc:
        _disable_redis(exc)
        logger.warning("Redis DELETE failed for key=%s", key)


async def cache_delete_prefix(prefix: str) -> None:
    """
    Delete all cache keys that start with a prefix.
    Use this after writes to avoid stale list/search caches.
    """
    if not settings.REDIS_URL:
        return
    try:
        r = await get_redis()
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        _disable_redis(exc)
        logger.warning("Redis DELETE PREFIX failed for prefix=%s", prefix)
