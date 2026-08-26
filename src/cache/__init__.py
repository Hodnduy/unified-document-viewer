"""Cache package.

Re-exports for convenient imports::

    from src.cache import init_redis, close_redis, get_cached, set_cached
"""
from src.cache.redis_client import close_redis, get_cached, init_redis, set_cached

__all__ = [
    "init_redis",
    "close_redis",
    "get_cached",
    "set_cached",
]
