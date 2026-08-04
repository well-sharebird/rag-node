import logging
from fastapi import APIRouter

from packages.core.deps import DBSession, RedisClient, MilvusDep
from packages.agent.services.stats_service import get_dashboard_stats, get_quality_metrics, get_top_documents
from packages.core.system.schemas.dashboard import DashboardStats, QualityMetrics, TopDocsResponse

logger = logging.getLogger("app.api.dashboard")
router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: DBSession, redis: RedisClient, milvus: MilvusDep):
    return await get_dashboard_stats(db, milvus, redis)


@router.get("/dashboard/quality", response_model=QualityMetrics)
async def quality_metrics(db: DBSession, redis: RedisClient):
    return await get_quality_metrics(redis)


@router.get("/dashboard/top-docs", response_model=TopDocsResponse)
async def top_documents(db: DBSession, redis: RedisClient):
    return await get_top_documents(db, redis)
