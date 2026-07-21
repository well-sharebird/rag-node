import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging_config import setup_logging
from app.core.milvus_client import get_milvus_client, close_milvus_client, check_milvus_health
from app.core.redis_client import close_redis
from app.core.minio_client import ensure_bucket
from app.core.rag_config import reload_from_db
from app.api.v1.router import router as v1_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.evaluation import router as evaluation_router
from app.utils.error_handlers import register_error_handlers

setup_logging(debug=settings.debug)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Starting up")

    # --- Database ---
    from app.core.database import engine
    from app.models.base import Base
    # Ensure all models are registered for table creation
    from app.models.feedback import Feedback
    from app.models.conversation import Conversation, ConversationMessage
    from app.models.evaluation import GoldenSample, EvaluationRun
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured | url=%s", settings.database_url[:30])

    # --- Load RAG Config from System Settings ---
    await reload_from_db()
    logger.info("RAG config loaded from system_settings")

    # --- Default Settings & Auth Init ---
    from app.core.database import async_session_factory
    from app.models.system_setting import SystemSetting
    from sqlalchemy import select, func

    # Init default settings
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(SystemSetting.id)))
            if result.scalar() == 0:
                from app.schemas.settings import SettingsObject
                session.add(SystemSetting(version=1, is_active=True, settings_json=SettingsObject().model_dump()))
                await session.commit()
                logger.info("Default settings initialized")
    except Exception as e:
        logger.warning("Settings init failed: %s", e)

    # Init auth (roles, permissions, admin user) - moved to startup event
    # Auth initialization will be done via API call or manual SQL script
    logger.info("Auth system ready (use /api/v1/users/init to initialize)")

    # --- MinIO ---
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning("MinIO init failed: %s", e)

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

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    close_milvus_client()
    await close_redis()

    from app.core.database import close_db
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
from app.core.observability import setup_observability
setup_observability(app)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(v1_router, prefix=settings.api_prefix)
app.include_router(feedback_router, prefix=settings.api_prefix)
app.include_router(conversations_router, prefix=settings.api_prefix)
app.include_router(evaluation_router, prefix=settings.api_prefix)
register_error_handlers(app)


@app.get("/")
async def root():
    return {"service": settings.app_name, "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
