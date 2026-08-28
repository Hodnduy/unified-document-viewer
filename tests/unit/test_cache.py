"""Unit tests for src/cache/redis_client.py – Redis cache module.

All tests mock the underlying ``redis.asyncio`` client so that no real
Redis server is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import src.cache.redis_client as cache_mod
from src.cache.redis_client import (
    close_redis,
    get_cached,
    init_redis,
    set_cached,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_redis_client():
    """Reset the module-level _redis_client before and after each test."""
    cache_mod._redis_client = None
    yield
    cache_mod._redis_client = None


# ---------------------------------------------------------------------------
# init_redis
# ---------------------------------------------------------------------------

class TestInitRedis:
    """Tests for the ``init_redis`` function."""

    async def test_successful_connection(self):
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True

        with patch("src.cache.redis_client.redis.from_url", return_value=mock_redis):
            await init_redis()

        mock_redis.ping.assert_awaited_once()
        assert cache_mod._redis_client is mock_redis

    async def test_connection_failure_sets_client_to_none(self):
        with patch(
            "src.cache.redis_client.redis.from_url",
            side_effect=Exception("Connection refused"),
        ):
            await init_redis()

        assert cache_mod._redis_client is None

    async def test_ping_failure_sets_client_to_none(self):
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Ping failed")

        with patch("src.cache.redis_client.redis.from_url", return_value=mock_redis):
            await init_redis()

        assert cache_mod._redis_client is None


# ---------------------------------------------------------------------------
# close_redis
# ---------------------------------------------------------------------------

class TestCloseRedis:
    """Tests for the ``close_redis`` function."""

    async def test_closes_active_connection(self):
        mock_redis = AsyncMock()
        cache_mod._redis_client = mock_redis

        await close_redis()

        mock_redis.close.assert_awaited_once()
        assert cache_mod._redis_client is None

    async def test_noop_when_no_client(self):
        cache_mod._redis_client = None
        await close_redis()  # should not raise
        assert cache_mod._redis_client is None


# ---------------------------------------------------------------------------
# get_cached
# ---------------------------------------------------------------------------

class TestGetCached:
    """Tests for the ``get_cached`` function."""

    async def test_returns_none_when_no_client(self):
        result = await get_cached("any_key")
        assert result is None

    async def test_returns_cached_value(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"key": "value"}'
        cache_mod._redis_client = mock_redis

        result = await get_cached("test_key")

        assert result == '{"key": "value"}'
        mock_redis.get.assert_awaited_once_with("test_key")

    async def test_returns_none_on_cache_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        cache_mod._redis_client = mock_redis

        result = await get_cached("missing_key")
        assert result is None

    async def test_returns_none_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis error")
        cache_mod._redis_client = mock_redis

        result = await get_cached("test_key")
        assert result is None


# ---------------------------------------------------------------------------
# set_cached
# ---------------------------------------------------------------------------

class TestSetCached:
    """Tests for the ``set_cached`` function."""

    async def test_noop_when_no_client(self):
        await set_cached("key", "value", 60)  # should not raise

    async def test_stores_value_with_ttl(self):
        mock_redis = AsyncMock()
        cache_mod._redis_client = mock_redis

        await set_cached("key", "value", 600)

        mock_redis.set.assert_awaited_once_with("key", "value", ex=600)

    async def test_stores_value_without_ttl(self):
        mock_redis = AsyncMock()
        cache_mod._redis_client = mock_redis

        await set_cached("key", "value", None)

        mock_redis.set.assert_awaited_once_with("key", "value", ex=None)

    async def test_silently_handles_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = Exception("Redis error")
        cache_mod._redis_client = mock_redis

        await set_cached("key", "value", 60)  # should not raise
