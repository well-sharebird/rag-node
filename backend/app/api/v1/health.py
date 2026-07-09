import logging
from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import DBSession, RedisClient, MilvusDep
from app.core.milvus_client import check_milvus_health
from app.core.redis_client import check_redis_health
from app.core.minio_client import check_minio_health

logger = logging.getLogger("app.api.health")
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: DBSession, redis: RedisClient, milvus: MilvusDep):
    from app.config import settings as app_settings
    checks = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        logger.warning("Health: postgres failed: %s", e)

    if await check_redis_health(redis):
        checks["redis"] = "ok"
    else:
        checks["redis"] = "unreachable"
        logger.debug("Health: redis unreachable")

    if check_milvus_health():
        checks["milvus"] = "ok"
    else:
        checks["milvus"] = "unreachable"
        logger.warning("Health: milvus unreachable")

    if check_minio_health():
        checks["minio"] = "ok"
    else:
        checks["minio"] = "unreachable"
        logger.warning("Health: minio unreachable")

    all_ok = all(v == "ok" for v in checks.values())
    status = "healthy" if all_ok else "degraded"
    logger.info("Health: %s %s", status, checks)
    return {"status": status, "checks": checks}
