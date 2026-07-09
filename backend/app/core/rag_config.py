"""RAG configuration cache loaded from system_settings at startup and on publish.

All RAG-related config (embedding, chunking, retrieval) is stored in the
system_settings DB table and managed through the System Settings UI.
Environment variables only control infrastructure connections.
"""
import logging
from threading import Lock

logger = logging.getLogger("app.rag_config")

_lock = Lock()
_config: dict = {
    "model": {
        "embedding_provider": "local",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dim": 1024,
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "llm_model": "Qwen2.5-72B",
    },
    "chunking": {
        "strategy": "semantic",
        "chunk_size": 512,
        "chunk_overlap": 50,
        "separators": ["\n\n", "\n", ".", " ", ""],
    },
    "retrieval": {
        "default_top_k": 10,
        "default_min_score": 0.6,
        "enable_rerank": True,
        "rerank_top_n": 3,
    },
    "security": {
        "max_upload_size_mb": 50,
        "allowed_formats": ["pdf", "docx", "txt", "md", "html"],
        "rate_limit_per_minute": 100,
        "search_timeout_ms": 5000,
        "log_retention_days": 30,
    },
}


def get_config() -> dict:
    """Return a deep copy of the current RAG config."""
    with _lock:
        import copy
        return copy.deepcopy(_config)


def get_model_config() -> dict:
    with _lock:
        return dict(_config["model"])


def get_chunking_config() -> dict:
    with _lock:
        return dict(_config["chunking"])


def get_retrieval_config() -> dict:
    with _lock:
        return dict(_config["retrieval"])


def get_security_config() -> dict:
    with _lock:
        return dict(_config["security"])


async def reload_from_db():
    """Reload config from the active system_settings row. Called at startup and on publish."""
    from app.core.database import async_session_factory
    from app.models.system_setting import SystemSetting
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(SystemSetting).where(SystemSetting.is_active == True)
                .order_by(SystemSetting.version.desc()).limit(1)
            )
            row = result.scalar_one_or_none()
            if row and row.settings_json:
                with _lock:
                    _config.clear()
                    _config.update(row.settings_json)
                logger.info("RAG config loaded from DB (version %d)", row.version)
                return row.settings_json
    except Exception as e:
        logger.warning("Failed to load RAG config from DB, using defaults: %s", e)
    return None
