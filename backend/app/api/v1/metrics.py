"""
Observability metrics and health endpoint
"""
from fastapi import APIRouter
import redis.asyncio as aioredis
from app.core.redis_client import get_redis_pool

router = APIRouter(tags=["Observability"])


@router.get("/metrics/health")
async def health_check():
    """Comprehensive health check."""
    from app.core.database import check_db_health
    from app.core.milvus_client import check_milvus_health
    from app.core.redis_client import check_redis_health

    db_ok = await check_db_health()
    milvus_ok = check_milvus_health()

    try:
        redis = await get_redis_pool()
        redis_ok = bool(redis) and await check_redis_health()
    except Exception:
        redis_ok = False

    all_ok = db_ok and milvus_ok and redis_ok

    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": {
            "database": "ok" if db_ok else "fail",
            "milvus": "ok" if milvus_ok else "fail",
            "redis": "ok" if redis_ok else "fail",
        },
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }


@router.get("/metrics/summary")
async def metrics_summary():
    """Get application metrics summary."""
    try:
        redis = await get_redis_pool()
        from app.core.observability import get_metrics_summary
        return await get_metrics_summary(redis)
    except Exception:
        return {
            "status": "unavailable",
            "message": "Metrics service temporarily unavailable",
        }


@router.get("/metrics/errors")
async def recent_errors(limit: int = 20):
    """Get recent error details."""
    try:
        redis = await get_redis_pool()
        if not redis:
            return {"items": [], "count": 0}

        raw = await redis.lrange("metrics:error_detail", 0, limit - 1)
        import json
        items = [json.loads(e) for e in raw]
        return {"items": items, "count": len(items)}
    except Exception:
        return {"items": [], "count": 0}
