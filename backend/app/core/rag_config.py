"""RAG configuration cache loaded from system_settings at startup and on publish.

All RAG-related config (chunking, retrieval, multimodal, security) is stored in the
system_settings DB table and managed through the System Settings UI.

Model configurations (embedding, rerank, LLM) are stored in the model_configs table
and managed through the Model Management UI. This file only contains application-level
settings, not model configurations.

Environment variables only control infrastructure connections (DB, Redis, Milvus, etc.).
"""
import logging
from threading import Lock

logger = logging.getLogger("app.rag_config")

_lock = Lock()
_config: dict = {
    # Chunking, retrieval, multimodal, security settings
    # These are loaded from system_settings DB table
    "chunking": {
        "strategy": "semantic",
        "chunk_size": 384,
        "chunk_overlap": 50,
        "separators": ["\n\n", "\n", ".", " ", ""],
    },
    "retrieval": {
        "default_top_k": 10,
        "default_min_score": 0.6,
        "enable_rerank": True,
        "rerank_top_n": 3,
    },
    "multimodal": {
        "enabled": True,
        "content_types": ["text", "table", "image"],
        "type_weights": {"text": 1.0, "table": 0.9, "image": 0.8},
        "max_images_per_doc": 50,
    },
    "security": {
        "max_upload_size_mb": 50,
        "allowed_formats": ["pdf", "docx", "xlsx", "pptx", "txt", "md", "html", "htm", "jpg", "jpeg", "png", "tiff", "tif", "bmp"],
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


def get_chunking_config() -> dict:
    with _lock:
        return dict(_config["chunking"])


def get_retrieval_config() -> dict:
    with _lock:
        return dict(_config["retrieval"])


def get_security_config() -> dict:
    with _lock:
        return dict(_config["security"])


def get_multimodal_config() -> dict:
    with _lock:
        return dict(_config.get("multimodal", {"enabled": True}))


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
        logger.warning("Failed to load RAG config from DB: %s", e)
    return None
