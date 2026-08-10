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
        # Increased timeout for remote MinIO server (100.4.14.19)
        # Support large file uploads (PPTX, etc.) with longer timeout
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=10.0, read=60.0),  # 连接 10 秒，读取 60 秒
            retries=urllib3.Retry(
                total=3,
                connect=3,
                read=3,
                backoff_factor=1.0,  # 1s, 2s, 4s 指数退避
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "POST"],
            ),
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
