"""Redis cache client with fail-safe design.

If Redis is unavailable, all operations silently degrade to no-ops
so that the application continues to function without caching.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


async def init_redis() -> None:
    """Initialise the Redis connection pool and verify connectivity.

    If Redis is unreachable the client is set to ``None`` and all
    subsequent cache operations become silent no-ops.
    """
    global _redis_client
    try:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        await _redis_client.ping()
        logger.info("Redis connected successfully at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable – caching disabled: %s", exc)
        _redis_client = None


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


async def get_cached(key: str) -> Optional[str]:
    """Return the cached value for *key*, or ``None`` on miss / error."""
    if _redis_client is None:
        return None
    try:
        return await _redis_client.get(key)
    except Exception as exc:
        logger.warning("Redis GET failed for key '%s': %s", key, exc)
        return None


async def set_cached(key: str, value: str, ttl: int | None = None) -> None:
    """Store *value* under *key* with an optional TTL (seconds).

    Failures are logged but never propagated to the caller.
    """
    if _redis_client is None:
        return
    try:
        await _redis_client.set(key, value, ex=ttl)
    except Exception as exc:
        logger.warning("Redis SET failed for key '%s': %s", key, exc)
