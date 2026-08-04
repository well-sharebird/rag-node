"""
Token Usage API Routes
Token 使用量追踪和管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from packages.core.database import get_db
from packages.core.auth import get_current_user, get_current_admin_user
from packages.core.system.models.user import User
from packages.model_gateway.models.token_usage import TokenUsage, UserQuota
from packages.model_gateway.models.model_gateway import ModelProvider
from packages.model_gateway.schemas.token_usage import (
    TokenUsageCreate,
    TokenUsageResponse,
    TokenUsageStats,
    UserQuotaSchema,
    UserQuotaUpdate,
    DashboardStats,
)
from packages.model_gateway.schemas.model_gateway import ModelProviderResponse, ModelProviderCreate
from packages.model_gateway.services.token_usage_service import TokenUsageService, QuotaService

router = APIRouter(prefix="/token-usage", tags=["token-usage"])


@router.post("/record", response_model=TokenUsageResponse)
async def record_token_usage(
    usage: TokenUsageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录 Token 使用（通常由系统内部调用）"""
    service = TokenUsageService(db)

    # Check quota if user is specified
    if usage.user_id:
        quota_service = QuotaService(db)
        allowed, reason = await quota_service.check_quota(
            usage.user_id,
            requested_tokens=usage.total_tokens,
            requested_cost=usage.cost,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

    db_usage = await service.record_usage(
        model_name=usage.model_name,
        model_type=usage.model_type,
        provider=usage.provider,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        request_type=usage.request_type,
        user_id=usage.user_id,
        api_key_id=usage.api_key_id,
        model_config_id=usage.model_config_id,
        cost=usage.cost,
        currency=usage.currency,
        endpoint=usage.endpoint,
        status=usage.status,
        error_message=usage.error_message,
        latency_ms=usage.latency_ms,
        response_id=usage.response_id,
    )

    return db_usage


@router.get("/my-stats", response_model=TokenUsageStats)
async def get_my_usage_stats(
    days: int = Query(default=7, ge=1, le=90),
    model_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的 Token 使用统计"""
    service = TokenUsageService(db)
    return await service.get_user_usage(
        user_id=current_user.id,
        days=days,
        model_type=model_type,
    )


@router.get("/my-trend")
async def get_my_usage_trend(
    days: int = Query(default=30, ge=1, le=90),
    model_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的 Token 使用趋势"""
    service = TokenUsageService(db)
    trend = await service.get_usage_trend(
        user_id=current_user.id,
        days=days,
        model_type=model_type,
    )
    return {"items": trend}


@router.get("/my-quota", response_model=UserQuotaSchema)
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的配额"""
    service = TokenUsageService(db)
    quota = await service.get_quota(user_id=current_user.id)

    if not quota:
        # Return default quota info
        return UserQuotaSchema(
            id=0,
            user_id=current_user.id,
            daily_token_limit=100000,
            daily_cost_limit=None,
            monthly_token_limit=1000000,
            monthly_cost_limit=None,
            used_daily_tokens=0,
            used_daily_cost=0.0,
            used_monthly_tokens=0,
            used_monthly_cost=0.0,
            daily_reset_at=None,
            monthly_reset_at=None,
            is_active=True,
            exceeded_action="block",
        )

    return quota


# Admin routes


@router.get("/admin/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """获取管理仪表盘统计（仅管理员）"""
    today_start = func.date(func.now())

    # Total users
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0

    # Active models
    result = await db.execute(
        select(func.count(TokenUsage.model_config_id.distinct()))
        .where(TokenUsage.created_at >= today_start)
    )
    active_models = result.scalar() or 0

    # Today's stats
    result = await db.execute(
        select(
            func.sum(TokenUsage.total_tokens),
            func.sum(TokenUsage.cost),
            func.count(TokenUsage.id),
        ).where(TokenUsage.created_at >= today_start)
    )
    row = result.first()
    total_tokens_today = row[0] or 0
    total_cost_today = row[1] or 0.0
    requests_today = row[2] or 0

    # Month stats (approximate)
    from datetime import timedelta
    month_start = func.now() - timedelta(days=30)

    result = await db.execute(
        select(
            func.sum(TokenUsage.total_tokens),
            func.sum(TokenUsage.cost),
        ).where(TokenUsage.created_at >= month_start)
    )
    row = result.first()
    total_tokens_month = row[0] or 0
    total_cost_month = row[1] or 0.0

    return DashboardStats(
        total_users=total_users,
        total_tokens_today=total_tokens_today,
        total_tokens_month=total_tokens_month,
        total_cost_today=total_cost_today,
        total_cost_month=total_cost_month,
        active_models=active_models,
        requests_today=requests_today,
    )


@router.get("/admin/users")
async def get_top_users(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """获取 Top 用户（仅管理员）"""
    service = TokenUsageService(db)
    users = await service.get_top_users(days=days, limit=limit)
    return {"items": users}


@router.get("/admin/quotas")
async def get_all_quotas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """获取所有用户配额（仅管理员）"""
    result = await db.execute(
        select(UserQuota, User.username, User.email)
        .join(User, UserQuota.user_id == User.id)
    )
    rows = result.all()

    items = []
    for quota, username, email in rows:
        items.append({
            "id": quota.id,
            "user_id": quota.user_id,
            "username": username,
            "email": email,
            "daily_token_limit": quota.daily_token_limit,
            "daily_cost_limit": quota.daily_cost_limit,
            "monthly_token_limit": quota.monthly_token_limit,
            "monthly_cost_limit": quota.monthly_cost_limit,
            "used_daily_tokens": quota.used_daily_tokens,
            "used_daily_cost": quota.used_daily_cost,
            "used_monthly_tokens": quota.used_monthly_tokens,
            "used_monthly_cost": quota.used_monthly_cost,
            "is_active": quota.is_active,
        })

    return {"items": items}


@router.post("/admin/quota/{user_id}", response_model=UserQuotaSchema)
async def set_user_quota(
    user_id: int,
    quota_data: UserQuotaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """设置用户配额（仅管理员）"""
    service = TokenUsageService(db)

    quota = await service.set_quota(
        user_id=user_id,
        daily_token_limit=quota_data.daily_token_limit,
        daily_cost_limit=quota_data.daily_cost_limit,
        monthly_token_limit=quota_data.monthly_token_limit,
        monthly_cost_limit=quota_data.monthly_cost_limit,
        exceeded_action=quota_data.exceeded_action or "block",
    )

    return UserQuotaSchema(
        id=quota.id,
        user_id=quota.user_id,
        daily_token_limit=quota.daily_token_limit,
        daily_cost_limit=quota.daily_cost_limit,
        monthly_token_limit=quota.monthly_token_limit,
        monthly_cost_limit=quota.monthly_cost_limit,
        used_daily_tokens=quota.used_daily_tokens,
        used_daily_cost=quota.used_daily_cost,
        used_monthly_tokens=quota.used_monthly_tokens,
        used_monthly_cost=quota.used_monthly_cost,
        daily_reset_at=quota.daily_reset_at,
        monthly_reset_at=quota.monthly_reset_at,
        is_active=quota.is_active,
        exceeded_action=quota.exceeded_action,
    )


@router.get("/admin/providers", response_model=list[ModelProviderResponse])
async def get_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """获取所有模型供应商（仅管理员）"""
    result = await db.execute(
        select(ModelProvider).order_by(ModelProvider.name)
    )
    providers = result.scalars().all()
    return providers


@router.post("/admin/providers", response_model=ModelProviderResponse)
async def create_provider(
    provider: ModelProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """创建模型供应商（仅管理员）"""
    import json

    db_provider = ModelProvider(
        name=provider.name,
        display_name=provider.display_name,
        provider_type=provider.provider_type,
        category=provider.category,
        api_base=provider.api_base,
        auth_type=provider.auth_type,
        pricing=json.dumps(provider.pricing) if provider.pricing else None,
        capabilities=json.dumps(provider.capabilities) if provider.capabilities else None,
        supported_models=json.dumps(provider.supported_models) if provider.supported_models else None,
        icon=provider.icon,
        description=provider.description,
    )

    db.add(db_provider)
    await db.commit()
    await db.refresh(db_provider)

    return db_provider
