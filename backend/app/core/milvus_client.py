import logging
from app.config import settings

logger = logging.getLogger("app.milvus")

_milvus_client = None


def get_milvus_client():
    """Returns a singleton MilvusClient with reduced connection timeout."""
    global _milvus_client
    if _milvus_client is None:
        from pymilvus import MilvusClient

        # Build connection parameters based on Milvus version compatibility
        client_kwargs = {
            "uri": settings.milvus_uri,
            "timeout": 3,  # Fast timeout for startup health check
        }

        # Milvus 2.5+ uses user/password instead of token
        if settings.milvus_user and settings.milvus_password:
            client_kwargs["user"] = settings.milvus_user
            client_kwargs["password"] = settings.milvus_password

        # db_name is supported in Milvus 2.3+
        if settings.milvus_db_name and settings.milvus_db_name != "default":
            client_kwargs["db_name"] = settings.milvus_db_name

        _milvus_client = MilvusClient(**client_kwargs)
        logger.info(
            "MilvusClient created | host=%s:%s db=%s user=%s",
            settings.milvus_host, settings.milvus_port,
            settings.milvus_db_name, settings.milvus_user or "none",
        )
    return _milvus_client


def close_milvus_client():
    """Close the Milvus client. pymilvus will release gRPC channels."""
    global _milvus_client
    if _milvus_client:
        _milvus_client.close()
        _milvus_client = None
        logger.info("MilvusClient closed")


def check_milvus_health() -> bool:
    try:
        client = get_milvus_client()
        client.list_collections()
        return True
    except Exception:
        return False
