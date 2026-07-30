"""
数据脱敏配置 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.desensitization_service import (
    DesensitizationService,
    DesensitizationConfig,
    DesensitizationLevel,
    get_kb_desensitization_config,
    save_kb_desensitization_config,
)

router = APIRouter(prefix="/desensitization", tags=["desensitization"])


class DesensitizationConfigRequest(BaseModel):
    """脱敏配置请求"""
    level: str = Field("medium", description="脱敏级别：none, low, medium, high")
    enable_email_mask: bool = True
    enable_phone_mask: bool = True
    enable_id_card_mask: bool = True
    enable_bank_card_mask: bool = True
    enable_address_mask: bool = False
    enable_name_mask: bool = False
    custom_replacements: list = Field(default_factory=list, description="自定义替换规则 [{'from': 'apple', 'to': '苹果'}]")


class DesensitizationConfigResponse(BaseModel):
    """脱敏配置响应"""
    kb_id: Optional[str]
    level: str
    enable_email_mask: bool
    enable_phone_mask: bool
    enable_id_card_mask: bool
    enable_bank_card_mask: bool
    enable_address_mask: bool
    enable_name_mask: bool


class DesensitizationTestRequest(BaseModel):
    """脱敏测试请求"""
    text: str


class DesensitizationTestResponse(BaseModel):
    """脱敏测试响应"""
    original: str
    desensitized: str
    detected_pii: dict
    risk_level: str


@router.get("/config", response_model=DesensitizationConfigResponse)
async def get_desensitization_config(
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取脱敏配置"""
    config = await get_kb_desensitization_config(db, kb_id)
    return DesensitizationConfigResponse(
        kb_id=config.kb_id,
        level=config.level.value,
        enable_email_mask=config.enable_email_mask,
        enable_phone_mask=config.enable_phone_mask,
        enable_id_card_mask=config.enable_id_card_mask,
        enable_bank_card_mask=config.enable_bank_card_mask,
        enable_address_mask=config.enable_address_mask,
        enable_name_mask=config.enable_name_mask,
    )


@router.put("/config", response_model=DesensitizationConfigResponse)
async def update_desensitization_config(
    data: DesensitizationConfigRequest,
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新脱敏配置"""
    config = DesensitizationConfig(
        kb_id=kb_id,
        level=DesensitizationLevel(data.level),
        enable_email_mask=data.enable_email_mask,
        enable_phone_mask=data.enable_phone_mask,
        enable_id_card_mask=data.enable_id_card_mask,
        enable_bank_card_mask=data.enable_bank_card_mask,
        enable_address_mask=data.enable_address_mask,
        enable_name_mask=data.enable_name_mask,
        custom_rules=data.custom_replacements,
    )
    await save_kb_desensitization_config(db, kb_id, config)
    return DesensitizationConfigResponse(
        kb_id=config.kb_id,
        level=config.level.value,
        enable_email_mask=config.enable_email_mask,
        enable_phone_mask=config.enable_phone_mask,
        enable_id_card_mask=config.enable_id_card_mask,
        enable_bank_card_mask=config.enable_bank_card_mask,
        enable_address_mask=config.enable_address_mask,
        enable_name_mask=config.enable_name_mask,
    )


@router.post("/test", response_model=DesensitizationTestResponse)
async def test_desensitization(
    data: DesensitizationTestRequest,
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """测试脱敏效果"""
    config = await get_kb_desensitization_config(db, kb_id)
    service = DesensitizationService(db, config)

    desensitized = service.apply(data.text)
    pii_stats = service.get_pii_statistics(data.text)

    return DesensitizationTestResponse(
        original=data.text,
        desensitized=desensitized,
        detected_pii=pii_stats["types"],
        risk_level=pii_stats["risk_level"],
    )
