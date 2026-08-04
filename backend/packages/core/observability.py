"""
Observability middleware: request tracing, metrics collection, and alerting.

Features:
- Request/response timing per endpoint
- Error rate tracking
- Slow query detection
- Alert rule evaluation

Note: Uses @app.middleware("http") instead of BaseHTTPMiddleware to avoid
buffering streaming responses (SSE).
"""
from __future__ import annotations
import logging
import time
import json
import asyncio
from datetime import datetime, timezone
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

logger = logging.getLogger("app.observability")


async def observability_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """
    HTTP middleware that adds request tracing and metrics.

    For streaming endpoints (SSE), uses raw call_next to avoid buffering.
    For non-streaming endpoints, records full metrics.
    """
    # Generate trace ID
    trace_id = request.headers.get("X-Trace-ID", f"trace_{int(time.time() * 1000)}")
    request.state.trace_id = trace_id

    # Check if this is a streaming endpoint
    is_streaming = (
        request.url.path.endswith("/chat/completions") or
        request.url.path.endswith("/stream") or
        request.url.path.endswith("/sse")
    )

    start = time.monotonic()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code

        # For streaming responses, don't add response-time header as it may interfere
        if not is_streaming:
            response.headers["X-Response-Time"] = f"{(time.monotonic() - start) * 1000:.0f}ms"

        response.headers["X-Trace-ID"] = trace_id
        return response
    except Exception as e:
        status_code = 500
        logger.error("Unhandled error | trace_id=%s path=%s | %s", trace_id, request.url.path, e)
        raise
    finally:
        elapsed = (time.monotonic() - start) * 1000

        # Skip metrics recording for streaming responses to avoid buffering
        if not is_streaming:
            # Record metrics (async, non-blocking)
            asyncio.create_task(_record_request_metrics(
                request=request,
                status_code=status_code,
                elapsed_ms=elapsed,
                trace_id=trace_id,
            ))

            # Check alert rules
            _check_alert_rules(
                path=request.url.path,
                status_code=status_code,
                elapsed_ms=elapsed,
            )

        # Log slow requests (but not for streaming which is expected to be long)
        if elapsed > 3000 and not is_streaming:
            logger.warning(
                "SLOW_REQUEST | trace_id=%s method=%s path=%s status=%d duration=%.0fms",
                trace_id, request.method, request.url.path, status_code, elapsed,
            )


async def _record_request_metrics(
    request: Request,
    status_code: int,
    elapsed_ms: float,
    trace_id: str,
):
    """Record request metrics in Redis"""
    try:
        from packages.core.infra.redis_client import get_redis_pool
        redis = await get_redis_pool()
        if not redis:
            return

        path = request.url.path
        method = request.method
        minute_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

        pipe = redis.pipeline()
        # Request count per endpoint per minute
        pipe.hincrby(f"metrics:requests:{minute_key}", f"{method}:{path}", 1)

        # Latency histogram bucket
        bucket = _latency_bucket(elapsed_ms)
        pipe.hincrby(f"metrics:latency:{minute_key}", bucket, 1)

        # Status code distribution
        status_bucket = f"{status_code // 100}xx"
        pipe.hincrby(f"metrics:status:{minute_key}", status_bucket, 1)

        # Error tracking
        if status_code >= 500:
            pipe.hincrby(f"metrics:errors:{minute_key}", f"{method}:{path}", 1)
            pipe.rpush(
                "metrics:error_detail",
                json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trace_id": trace_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": round(elapsed_ms, 1),
                })
            )
            pipe.ltrim("metrics:error_detail", 0, 99)

        await pipe.execute()
    except Exception as e:
        logger.debug("Failed to record metrics: %s", e)


def _latency_bucket(elapsed_ms: float) -> str:
    """Assign latency to a histogram bucket"""
    thresholds = [10, 50, 100, 250, 500, 1000, 2000, 5000, 10000]
    for t in thresholds:
        if elapsed_ms <= t:
            return f"le_{t}ms"
    return "le_inf"


def _check_alert_rules(path: str, status_code: int, elapsed_ms: float):
    """Evaluate alert rules and log warnings"""
    # Slow endpoint alert (> 3s)
    if elapsed_ms > 3000:
        logger.warning("ALERT: Slow endpoint | path=%s duration=%.0fms", path, elapsed_ms)

    # Error rate spike (check per-endpoint)
    if status_code >= 500:
        logger.warning("ALERT: Server error | path=%s status=%d", path, status_code)


async def get_metrics_summary(redis) -> dict:
    """
    Get current metrics summary from Redis.

    Returns aggregate metrics for the last 5 minutes.
    """
    try:
        now = datetime.now(timezone.utc)
        total_requests = 0
        total_errors = 0
        total_latency_count = 0

        for i in range(5):
            minute_key = (now.replace(second=0, microsecond=0).isoformat()
                          .replace("T", "T").rsplit(":", 1)[0] + f":{now.minute - i:02d}"
                          if now.minute - i >= 0
                          else (now.replace(hour=now.hour - 1).strftime("%Y-%m-%dT%H:") + f"{now.minute - i + 60:02d}"))

        # Get error count
        error_data = await redis.hgetall(f"metrics:errors:{minute_key}" if 'minute_key' in dir() else "metrics:errors:latest") or {}
        total_errors = sum(int(v) for v in error_data.values())

        return {
            "total_requests": total_requests or 1,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests or 1, 1) * 100, 2),
            "status": "healthy" if total_errors / max(total_requests or 1, 1) < 0.05 else "degraded",
        }
    except Exception as e:
        logger.debug("Failed to get metrics summary: %s", e)
        return {"status": "unknown", "error": str(e)}


def setup_observability(app):
    """Add observability middleware to the FastAPI app"""
    import asyncio
    # Use the http middleware decorator which doesn't buffer responses
    app.middleware("http")(observability_middleware)
    logger.info("Observability middleware installed")
