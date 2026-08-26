"""Global test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_redis_cache():
    """Ensure Redis is always disabled during tests.

    This prevents tests from accidentally connecting to a real Redis
    server running on the developer's machine.
    """
    import src.cache.redis_client as cache_mod

    original = cache_mod._redis_client
    cache_mod._redis_client = None
    yield
    cache_mod._redis_client = original
