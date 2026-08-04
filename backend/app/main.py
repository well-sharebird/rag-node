import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.core.config import settings
from packages.core.logging_config import setup_logging
from packages.core.infra.milvus_client import get_milvus_client, close_milvus_client, check_milvus_health
from packages.core.infra.redis_client import close_redis
from packages.core.infra.minio_client import ensure_bucket
from packages.rag.config import reload_from_db
from app.api.v1.router import router as v1_router
from packages.core.error_handlers import register_error_handlers

setup_logging(debug=settings.debug)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Starting up")

    # --- Database ---
    from packages.core.database import engine
    from packages.core.base_model import Base
    # Ensure all models are registered for table creation
    from packages.agent.models.feedback import Feedback
    from packages.agent.models.conversation import Conversation, ConversationMessage
    from packages.rag.models.evaluation import GoldenSample, EvaluationRun
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured | url=%s", settings.database_url[:30])

    # --- Load RAG Config from System Settings ---
    rag_config = await reload_from_db()
    logger.info("RAG config loaded from system_settings")

    # --- Initialize FileTypeRouter from settings ---
    from packages.rag.services.file_type_router import init_router_from_settings
    try:
        file_type_routes = rag_config.get("chunking", {}).get("file_type_routes", {}) if rag_config else {}
        if file_type_routes:
            init_router_from_settings(file_type_routes)
            logger.info("FileTypeRouter initialized with %d custom routes", len(file_type_routes))
        else:
            from packages.rag.services.file_type_router import get_router
            get_router()  # Initialize with defaults
            logger.info("FileTypeRouter initialized with default routes")
    except Exception as e:
        logger.warning("FileTypeRouter init failed: %s", e)

    # --- Default Settings & Auth Init ---
    from packages.core.database import async_session_factory
    from packages.core.system.models.system_setting import SystemSetting
    from sqlalchemy import select, func

    # Init default settings
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(SystemSetting.id)))
            if result.scalar() == 0:
                from packages.core.system.schemas.settings import SettingsObject
                session.add(SystemSetting(version=1, is_active=True, settings_json=SettingsObject().model_dump()))
                await session.commit()
                logger.info("Default settings initialized")
    except Exception as e:
        logger.warning("Settings init failed: %s", e)

    # --- Initialize Default Agents ---
    from packages.agent.services.agent_bootstrap import init_system_agents
    try:
        async with async_session_factory() as session:
            await init_system_agents(session)
        logger.info("Default agents initialized")
    except Exception as e:
        logger.warning("Default agents init failed: %s", e)

    # --- Initialize Default Synonyms ---
    from packages.rag.services.synonym_service import init_default_synonyms
    try:
        async with async_session_factory() as session:
            await init_default_synonyms(session)
        logger.info("Default synonyms initialized")
    except Exception as e:
        logger.warning("Default synonyms init failed: %s", e)

    # Init auth (roles, permissions, admin user) - moved to startup event
    # Auth initialization will be done via API call or manual SQL script
    logger.info("Auth system ready (use /api/v1/users/init to initialize)")

    # --- MinIO ---
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning("MinIO init failed: %s", e)

    # --- Initialize Global Trace Service ---
    from packages.core.tracing import init_global_trace_service, ensure_trace_index
    from packages.core.infra.es_client import get_es_client
    try:
        es_client = get_es_client()
        init_global_trace_service(es_client)
        await ensure_trace_index()
        logger.info("Global trace service initialized")
    except Exception as e:
        logger.warning("Trace service init failed: %s", e)

    # --- Milvus ---
    try:
        client = get_milvus_client()
        collections = client.list_collections()
        logger.info("Milvus connected | collections=%d", len(collections))
    except Exception as e:
        logger.warning("Milvus init failed: %s", e)

    # --- Health Summary ---
    db_ok = True  # already passed table creation
    milvus_ok = check_milvus_health()
    logger.info("Health summary | postgres=%s milvus=%s", db_ok, milvus_ok)
    logger.info("=" * 60)

    # --- Model Health Monitor ---
    from packages.model_gateway.services.model_health_monitor import start_monitor, stop_monitor
    await start_monitor(
        db_session_factory=async_session_factory,
        check_interval_seconds=settings.model_health_check_interval,
        check_timeout_ms=settings.model_health_check_timeout,
        max_concurrent_checks=settings.model_health_check_concurrency,
    )
    logger.info(
        "Model health monitor started | interval=%ds timeout=%dms concurrency=%d",
        settings.model_health_check_interval,
        settings.model_health_check_timeout,
        settings.model_health_check_concurrency,
    )

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")

    # Stop model health monitor
    await stop_monitor()
    logger.info("Model health monitor stopped")

    close_milvus_client()
    await close_redis()

    from packages.core.database import close_db
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(title=settings.app_name, docs_url="/docs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add observability tracing middleware
from packages.core.observability import setup_observability
setup_observability(app)

app.include_router(v1_router, prefix=settings.api_prefix)
register_error_handlers(app)


@app.get("/")
async def root():
    return {"service": settings.app_name, "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
