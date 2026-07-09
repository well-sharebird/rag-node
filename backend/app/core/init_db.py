"""Initialize database tables. Run once before starting the app."""
from __future__ import annotations
from sqlalchemy import text
from app.core.database import engine, async_session_factory
from app.models.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.system_setting import SystemSetting, SettingHistory


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Insert default settings if not exists
    async with async_session_factory() as session:
        from app.models.system_setting import SystemSetting
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(SystemSetting.id)))
        count = result.scalar()
        if count == 0:
            from app.schemas.settings import SettingsObject
            setting = SystemSetting(
                version=1,
                is_active=True,
                settings_json=SettingsObject().model_dump(),
            )
            session.add(setting)
            await session.commit()


if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    print("Database initialized successfully.")
