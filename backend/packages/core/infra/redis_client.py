import logging
import redis.asyncio as aioredis
from packages.core.config import settings

logger = logging.getLogger("app.redis")

_pool: aioredis.ConnectionPool | None = None
_redis: aioredis.Redis | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            max_connections=settings.redis_pool_size,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            retry_on_timeout=settings.redis_retry_on_timeout,
            health_check_interval=settings.redis_health_check_interval,
            decode_responses=True,
        )
        logger.info(
            "Redis connection pool created | %s:%s db=%s max=%d",
            settings.redis_host, settings.redis_port, settings.redis_db, settings.redis_pool_size,
        )
    return _pool


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency: returns a shared Redis client backed by a connection pool."""
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(connection_pool=_get_pool())
    return _redis


async def get_redis_pool() -> aioredis.Redis:
    """Get Redis connection (alias for get_redis)."""
    return await get_redis()


async def close_redis():
    """Close the Redis connection pool on shutdown."""
    global _redis, _pool
    if _redis:
        await _redis.close()
        _redis = None
    if _pool:
        await _pool.disconnect()
        _pool = None
    logger.info("Redis connection pool closed")


async def check_redis_health(redis: aioredis.Redis | None = None) -> bool:
    try:
        r = redis or await get_redis()
        await r.ping()
        return True
    except Exception:
        return False
