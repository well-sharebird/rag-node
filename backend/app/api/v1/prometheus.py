"""
Prometheus metrics endpoint
Standard /metrics endpoint for Prometheus scraping
"""
from fastapi import APIRouter, Response
from app.core.prometheus_client import (
    get_prometheus_metrics,
    get_metrics_content_type,
    MILVUS_CONNECTIONS,
    MILVUS_COLLECTION_COUNT,
    REDIS_CONNECTIONS,
    REDIS_MEMORY_USAGE,
    POSTGRES_CONNECTIONS,
    USER_COUNT,
    ACTIVE_USERS,
)
from app.core.database import async_session_factory
from app.core.milvus_client import get_milvus_client
from app.core.redis_client import get_redis_pool
from sqlalchemy import select, func
from app.models.user import User
from datetime import datetime, timedelta
import json

router = APIRouter(tags=["Observability"])


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus exposition format.

    Standard endpoint for Prometheus scraping.
    See: https://prometheus.io/docs/instrumenting/exposition_formats/
    """
    from app.core.prometheus_client import get_prometheus_metrics, get_metrics_content_type

    # Update dynamic metrics
    await update_system_metrics()

    metrics = get_prometheus_metrics()
    return Response(
        content=metrics,
        media_type=get_metrics_content_type()
    )


@router.get("/metrics/json")
async def metrics_json():
    """
    Human-readable JSON metrics.
    For debugging and manual inspection.
    """
    from app.core.prometheus_client import REGISTRY

    metrics = {}

    # Update dynamic metrics
    await update_system_metrics()

    # Collect all metrics
    for collector in REGISTRY._names_to_collectors.values():
        try:
            for metric in collector.collect():
                for sample in metric.samples:
                    key = f"{sample.name}_".replace("__", "_")
                    if hasattr(sample, 'value'):
                        metrics[key] = float(sample.value)
        except Exception:
            continue

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics
    }


async def update_system_metrics():
    """Update dynamic system metrics"""
    try:
        # Update Milvus metrics
        try:
            client = get_milvus_client()
            collections = client.list_collections()
            MILVUS_COLLECTION_COUNT.set(len(collections))
            MILVUS_CONNECTIONS.set(1)

            # Update vector count per collection
            for coll in collections:
                try:
                    stats = client.get_query_segment_info(coll)
                    vector_count = sum(seg.num_rows for seg in stats.segments)
                    MILVUS_VECTOR_COUNT.labels(collection=coll).set(vector_count)
                except Exception:
                    pass
        except Exception:
            MILVUS_CONNECTIONS.set(0)

        # Update Redis metrics
        try:
            redis = await get_redis_pool()
            if redis:
                info = await redis.info('memory')
                REDIS_MEMORY_USAGE.set(info.get('used_memory', 0))
                REDIS_CONNECTIONS.set(1)
        except Exception:
            REDIS_CONNECTIONS.set(0)

        # Update PostgreSQL metrics
        try:
            async with async_session_factory() as session:
                result = await session.execute(select(func.count(User.id)))
                USER_COUNT.set(result.scalar() or 0)
            POSTGRES_CONNECTIONS.set(1)
        except Exception:
            POSTGRES_CONNECTIONS.set(0)

    except Exception as e:
        pass  # Silently ignore metric update errors
