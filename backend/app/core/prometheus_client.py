"""
Prometheus metrics client
Provides standard /metrics endpoint for Prometheus scraping
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry
import time
from typing import Optional

# =============================================================================
# Metrics Definitions
# =============================================================================

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

REQUEST_IN_PROGRESS = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['method', 'endpoint']
)

# RAG-specific metrics
RAG_RETRIEVAL_COUNT = Counter(
    'rag_retrievals_total',
    'Total RAG retrieval operations',
    ['knowledge_base', 'search_type']
)

RAG_RETRIEVAL_LATENCY = Histogram(
    'rag_retrieval_duration_seconds',
    'RAG retrieval latency in seconds',
    ['knowledge_base'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

RAG_RELEVANCE_SCORE = Histogram(
    'rag_relevance_score',
    'RAG retrieval relevance scores',
    ['knowledge_base'],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
)

# Document processing metrics
DOCUMENT_COUNT = Counter(
    'documents_processed_total',
    'Total documents processed',
    ['status', 'kb_id']
)

DOCUMENT_PROCESSING_LATENCY = Histogram(
    'document_processing_duration_seconds',
    'Document processing latency in seconds',
    ['status'],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0)
)

# Vector database metrics
MILVUS_CONNECTIONS = Gauge(
    'milvus_connections_active',
    'Active Milvus connections'
)

MILVUS_COLLECTION_COUNT = Gauge(
    'milvus_collections_total',
    'Total Milvus collections'
)

MILVUS_VECTOR_COUNT = Gauge(
    'milvus_vectors_total',
    'Total vectors in Milvus',
    ['collection']
)

# Redis metrics
REDIS_CONNECTIONS = Gauge(
    'redis_connections_active',
    'Active Redis connections'
)

REDIS_MEMORY_USAGE = Gauge(
    'redis_memory_usage_bytes',
    'Redis memory usage in bytes'
)

# PostgreSQL metrics
POSTGRES_CONNECTIONS = Gauge(
    'postgres_connections_active',
    'Active PostgreSQL connections'
)

POSTGRES_QUERY_LATENCY = Histogram(
    'postgres_query_duration_seconds',
    'PostgreSQL query latency in seconds',
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

# System metrics
SYSTEM_UPTIME = Gauge(
    'system_uptime_seconds',
    'System uptime in seconds'
)

SYSTEM_START_TIME = Gauge(
    'system_start_time_seconds',
    'System start time as Unix timestamp'
)

# Error metrics
ERROR_COUNT = Counter(
    'errors_total',
    'Total errors',
    ['type', 'endpoint']
)

# User metrics
USER_COUNT = Gauge(
    'users_total',
    'Total registered users'
)

ACTIVE_USERS = Gauge(
    'users_active',
    'Active users in last N minutes',
    ['window_minutes']
)

# =============================================================================
# Helper Functions
# =============================================================================

def record_request(method: str, endpoint: str, status: int, latency: float):
    """Record HTTP request metrics"""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)


def start_request_timer(method: str, endpoint: str):
    """Start request timer, returns stop function"""
    REQUEST_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
    start_time = time.time()

    def stop():
        REQUEST_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()
        return time.time() - start_time

    return stop


def record_rag_retrieval(kb: str, search_type: str, latency: float, score: Optional[float] = None):
    """Record RAG retrieval metrics"""
    RAG_RETRIEVAL_COUNT.labels(knowledge_base=kb, search_type=search_type).inc()
    RAG_RETRIEVAL_LATENCY.labels(knowledge_base=kb).observe(latency)
    if score is not None:
        RAG_RELEVANCE_SCORE.labels(knowledge_base=kb).observe(score)


def record_document_processed(status: str, kb_id: str, latency: float):
    """Record document processing metrics"""
    DOCUMENT_COUNT.labels(status=status, kb_id=kb_id).inc()
    DOCUMENT_PROCESSING_LATENCY.labels(status=status).observe(latency)


def record_error(error_type: str, endpoint: str):
    """Record error metrics"""
    ERROR_COUNT.labels(type=error_type, endpoint=endpoint).inc()


def get_prometheus_metrics() -> bytes:
    """Generate Prometheus format metrics"""
    return generate_latest()


def get_metrics_content_type() -> str:
    """Get Prometheus content type"""
    return CONTENT_TYPE_LATEST


# Initialize system metrics
SYSTEM_START_TIME.set(time.time())
SYSTEM_UPTIME.set_function(lambda: time.time() - SYSTEM_START_TIME._value.get())
