import logging
from app.config import settings

logger = logging.getLogger("app.milvus")

_milvus_client = None


def get_milvus_client():
    """Returns a singleton MilvusClient. pymilvus manages its own gRPC connection pool internally."""
    global _milvus_client
    if _milvus_client is None:
        from pymilvus import MilvusClient
        _milvus_client = MilvusClient(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            db_name=settings.milvus_db_name,
        )
        logger.info(
            "MilvusClient connected | host=%s:%s db=%s",
            settings.milvus_host, settings.milvus_port, settings.milvus_db_name,
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
