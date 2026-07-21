import logging
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

logger = logging.getLogger("app.database")

# PostgreSQL connection pool via asyncpg
engine = create_async_engine(
    settings.database_url,
    echo=False,
    **settings.database_connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


async def get_db():
    """FastAPI dependency: yields a database session with auto-commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except sqlalchemy_exc.SQLAlchemyError:
            logger.exception("Database error, rolling back")
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise


async def close_db():
    """Gracefully dispose the connection pool on shutdown."""
    logger.info("Disposing database connection pool")
    await engine.dispose()


async def check_db_health() -> bool:
    """Check PostgreSQL connectivity."""
    try:
        from sqlalchemy import text as sql_text
        async with async_session_factory() as session:
            await session.execute(sql_text("SELECT 1"))
            return True
    except Exception:
        return False
