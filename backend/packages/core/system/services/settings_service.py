from __future__ import annotations
import json
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from packages.core.system.models.system_setting import SystemSetting, SettingHistory
from packages.core.system.schemas.settings import (
    SettingsObject, SettingsUpdateRequest, SettingsResponse, SettingsHistoryItem,
)

logger = logging.getLogger("app.services.settings")

SETTINGS_CACHE_KEY = "rag:settings:active"
SETTINGS_CACHE_TTL = 30


def _default_settings_json() -> dict:
    return SettingsObject().model_dump()


async def _load_active_from_db(db: AsyncSession) -> SystemSetting | None:
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.is_active == True)
        .order_by(SystemSetting.version.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _try_get_cache(redis):
    try:
        cached = await redis.get(SETTINGS_CACHE_KEY)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug("Redis cache read failed: %s", e)
    return None


async def _try_set_cache(redis, data):
    try:
        await redis.setex(SETTINGS_CACHE_KEY, SETTINGS_CACHE_TTL, data)
    except Exception as e:
        logger.debug("Redis cache write failed: %s", e)


async def _init_default_settings(db: AsyncSession) -> SystemSetting:
    setting = SystemSetting(version=1, is_active=True, settings_json=_default_settings_json())
    db.add(setting)
    await db.flush()
    logger.info("Default settings initialized")
    return setting


async def get_active_settings(db: AsyncSession, redis) -> SettingsResponse:
    cached = await _try_get_cache(redis)
    if cached:
        return SettingsResponse(**cached)

    setting = await _load_active_from_db(db)
    if setting is None:
        setting = await _init_default_settings(db)

    response = SettingsResponse(
        version=setting.version, is_active=setting.is_active,
        settings=SettingsObject(**setting.settings_json), published_at=setting.published_at,
    )
    await _try_set_cache(redis, response.model_dump_json())
    return response


async def update_settings(db: AsyncSession, redis, data: SettingsUpdateRequest) -> SettingsResponse:
    current = await _load_active_from_db(db)
    if current is None:
        current = await _init_default_settings(db)

    current_json = dict(current.settings_json)
    update_data = data.model_dump(exclude_unset=True)
    _deep_merge(current_json, update_data)

    new_version = current.version + 1
    await db.execute(update(SystemSetting).where(SystemSetting.is_active == True).values(is_active=False))

    new_setting = SystemSetting(version=new_version, is_active=True, settings_json=current_json)
    db.add(new_setting)

    history = SettingHistory(version=new_version, action="published", settings_json=current_json)
    db.add(history)

    await db.flush()

    try:
        await redis.delete(SETTINGS_CACHE_KEY)
    except Exception as e:
        logger.debug("Failed to clear settings cache: %s", e)

    logger.info("Settings published | version=%d", new_version)

    # Reload rag_config cache so embedding/chunking/retrieval pick up changes
    from packages.rag.config import reload_from_db
    from packages.rag.services.embedding_service import reset_embedding_service
    await reload_from_db()
    reset_embedding_service()
    return SettingsResponse(
        version=new_setting.version, is_active=True,
        settings=SettingsObject(**current_json), published_at=new_setting.created_at,
    )


async def get_settings_history(db: AsyncSession) -> list[SettingsHistoryItem]:
    result = await db.execute(select(SettingHistory).order_by(SettingHistory.created_at.desc()).limit(50))
    return [SettingsHistoryItem.model_validate(row) for row in result.scalars().all()]


def _deep_merge(base: dict, update: dict):
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
