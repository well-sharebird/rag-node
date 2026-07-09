from __future__ import annotations
import logging
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.core.milvus_client import check_milvus_health
from app.core.redis_client import check_redis_health
from app.core.minio_client import check_minio_health
from app.config import settings as app_settings
from app.schemas.dashboard import DashboardStats, ServiceStatus, QualityMetrics, QualityTrendPoint, TopDocItem, TopDocsResponse

logger = logging.getLogger("app.services.stats")


async def get_dashboard_stats(db: AsyncSession, milvus, redis: aioredis.Redis) -> DashboardStats:
    total_kb = (await db.execute(select(func.count(KnowledgeBase.id)))).scalar() or 0
    total_doc = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_vec = (await db.execute(select(func.sum(KnowledgeBase.vector_count)))).scalar() or 0

    postgres_status = "healthy"
    try:
        await db.execute(select(func.now()))
    except Exception as e:
        postgres_status = "unhealthy"
        logger.warning("PG health check failed: %s", e)

    milvus_status = "healthy" if check_milvus_health() else "unhealthy"
    redis_status = "healthy" if await check_redis_health(redis) else "unhealthy"

    avg_latency = 0.0
    try:
        latencies = await redis.lrange("rag:latency:recent", 0, -1)
        if latencies:
            avg_latency = sum(float(l) for l in latencies) / len(latencies)
    except Exception as e:
        logger.debug("Redis latency read failed: %s", e)

    return DashboardStats(
        total_knowledge_bases=total_kb,
        total_documents=total_doc,
        total_vectors=int(total_vec or 0),
        avg_latency_ms=round(avg_latency, 1),
        services=ServiceStatus(milvus=milvus_status, postgres=postgres_status, redis=redis_status),
    )


async def get_quality_metrics(redis: aioredis.Redis) -> QualityMetrics:
    now = datetime.now(timezone.utc)
    trend = []
    total_searches = 0
    total_score = 0.0
    total_latency = 0.0
    zero_results = 0

    for day_offset in range(6, -1, -1):
        date_key = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        try:
            raw = await redis.get(f"rag:stats:{date_key}")
            data = json.loads(raw) if raw else {"searches": 0, "total_score": 0, "total_latency": 0, "zero_results": 0}
        except Exception:
            data = {"searches": 0, "total_score": 0, "total_latency": 0, "zero_results": 0}

        avg_score = (data["total_score"] / data["searches"]) if data["searches"] > 0 else 0.0
        trend.append(QualityTrendPoint(date=date_key, avg_score=round(avg_score, 3), search_count=data["searches"]))
        total_searches += data["searches"]
        total_score += data["total_score"]
        total_latency += data["total_latency"]
        zero_results += data["zero_results"]

    return QualityMetrics(
        avg_score_7d=round(total_score / total_searches, 3) if total_searches > 0 else 0.0,
        avg_latency_7d=round(total_latency / total_searches, 1) if total_searches > 0 else 0.0,
        total_searches_7d=total_searches,
        zero_result_rate=round(zero_results / total_searches, 3) if total_searches > 0 else 0.0,
        trend=trend,
    )


async def get_top_documents(db: AsyncSession, redis: aioredis.Redis) -> TopDocsResponse:
    try:
        raw = await redis.zrevrange("rag:top_docs", 0, 9, withscores=True)
    except Exception:
        raw = []

    items = []
    for doc_key, count in raw:
        parts = doc_key.split(":", 1)
        doc_id = parts[0] if parts else doc_key
        kb_name = "Unknown"
        doc_name = doc_key
        avg_score = 0.0

        try:
            score_raw = await redis.get(f"rag:doc_score:{doc_id}")
            if score_raw:
                data = json.loads(score_raw)
                avg_score = data.get("avg_score", 0.0)
        except Exception:
            pass

        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc:
            doc_name = doc.original_name
            kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
            kb = kb_result.scalar_one_or_none()
            if kb:
                kb_name = kb.name

        items.append(TopDocItem(
            doc_id=doc_id, doc_name=doc_name, kb_name=kb_name,
            search_count=int(count), avg_score=round(avg_score, 3),
        ))

    return TopDocsResponse(items=items)
