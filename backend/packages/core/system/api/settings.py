from __future__ import annotations
from fastapi import APIRouter

from packages.core.deps import DBSession, RedisClient
from packages.core.system.services import settings_service
from packages.core.system.schemas.settings import (
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsHistoryItem,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(db: DBSession, redis: RedisClient):
    return await settings_service.get_active_settings(db, redis)


@router.put("", response_model=SettingsResponse)
async def update_settings(db: DBSession, redis: RedisClient, data: SettingsUpdateRequest):
    return await settings_service.update_settings(db, redis, data)


@router.get("/history", response_model=list[SettingsHistoryItem])
async def get_settings_history(db: DBSession):
    return await settings_service.get_settings_history(db)
