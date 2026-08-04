import logging
from typing import AsyncGenerator, Generator
from sqlalchemy import exc as sqlalchemy_exc, text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from packages.core.config import settings

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

# Sync engine for operations that require synchronous session
sync_engine = create_engine(
    settings.database_url.replace("+asyncpg", ""),
    echo=False,
    pool_pre_ping=True,
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a database session with auto-commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
        except sqlalchemy_exc.SQLAlchemyError:
            logger.exception("Database error, rolling back")
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a synchronous database session."""
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except sqlalchemy_exc.SQLAlchemyError:
        logger.exception("Database error, rolling back")
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def close_db():
    """Gracefully dispose the connection pool on shutdown."""
    logger.info("Disposing database connection pool")
    await engine.dispose()


async def check_db_health() -> bool:
    """Check PostgreSQL connectivity."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False
