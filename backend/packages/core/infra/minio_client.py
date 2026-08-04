import logging
from minio import Minio
from packages.core.config import settings

logger = logging.getLogger("app.minio")

_minio_client: Minio | None = None


def get_minio_client() -> Minio:
    """Returns a singleton MinIO client. The underlying urllib3 PoolManager handles HTTP keep-alive."""
    global _minio_client
    if _minio_client is None:
        import urllib3
        # Use smaller retry count and timeout for faster startup
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=2.0, read=5.0),
            retries=urllib3.Retry(total=1, connect=1, backoff_factor=0.3),
        )
        _minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region="us-east-1",
            http_client=http_client,
        )
        logger.info(
            "MinIO client created | endpoint=%s bucket=%s",
            settings.minio_endpoint, settings.minio_bucket,
        )
    return _minio_client


def ensure_bucket():
    """Ensure the target bucket exists on startup."""
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("MinIO bucket created: %s", settings.minio_bucket)
    else:
        logger.info("MinIO bucket verified: %s", settings.minio_bucket)


def check_minio_health() -> bool:
    try:
        client = get_minio_client()
        client.list_buckets()
        return True
    except Exception:
        return False
