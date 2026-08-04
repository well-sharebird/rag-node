"""
Token Usage Tracking Service
记录和统计 Token 使用情况
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.model_gateway.models.token_usage import TokenUsage, UserQuota
from packages.model_gateway.models.model_gateway import ModelProvider
from packages.model_gateway.models.model_config import ModelConfig
from packages.core.system.models.user import User, APIKey
from packages.model_gateway.schemas.token_usage import TokenUsageCreate, TokenUsageStats, UserQuotaSchema


class TokenUsageService:
    """Token 使用量服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_usage(
        self,
        model_name: str,
        model_type: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        request_type: str,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        model_config_id: Optional[int] = None,
        cost: float = 0.0,
        currency: str = "USD",
        endpoint: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        latency_ms: Optional[int] = None,
        response_id: Optional[str] = None,
    ) -> TokenUsage:
        """记录一次 Token 使用"""
        total_tokens = input_tokens + output_tokens

        usage = TokenUsage(
            user_id=user_id,
            api_key_id=api_key_id,
            model_config_id=model_config_id,
            model_name=model_name,
            model_type=model_type,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            currency=currency,
            request_type=request_type,
            endpoint=endpoint,
            status=status,
            error_message=error_message,
            latency_ms=latency_ms,
            response_id=response_id,
        )

        self.db.add(usage)
        await self.db.commit()
        await self.db.refresh(usage)

        # Update user quota usage
        if user_id:
            await self._update_user_quota(user_id, total_tokens, cost)

        return usage

    async def _update_user_quota(self, user_id: int, tokens: int, cost: float):
        """更新用户配额使用量"""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()

        if not quota:
            # Create default quota if not exists
            quota = UserQuota(
                user_id=user_id,
                daily_token_limit=100000,  # Default 100k tokens/day
                monthly_token_limit=1000000,  # Default 1M tokens/month
                daily_reset_at=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                monthly_reset_at=datetime.utcnow().replace(day=1) + timedelta(days=32),
            )
            self.db.add(quota)
        else:
            # Reset if needed
            now = datetime.utcnow()
            if quota.daily_reset_at and now >= quota.daily_reset_at:
                quota.used_daily_tokens = 0
                quota.used_daily_cost = 0.0
                quota.daily_reset_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

            if quota.monthly_reset_at and now >= quota.monthly_reset_at:
                quota.used_monthly_tokens = 0
                quota.used_monthly_cost = 0.0
                # Next month same day
                if now.month == 12:
                    quota.monthly_reset_at = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    quota.monthly_reset_at = now.replace(month=now.month + 1, day=1)

            quota.used_daily_tokens += tokens
            quota.used_daily_cost += cost
            quota.used_monthly_tokens += tokens
            quota.used_monthly_cost += cost

        await self.db.commit()

    async def get_user_usage(
        self,
        user_id: int,
        days: int = 7,
        model_type: Optional[str] = None,
    ) -> TokenUsageStats:
        """获取用户使用统计"""
        start_date = datetime.utcnow() - timedelta(days=days)

        query = select(
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.input_tokens).label("input_tokens"),
            func.sum(TokenUsage.output_tokens).label("output_tokens"),
            func.sum(TokenUsage.cost).label("total_cost"),
            func.count(TokenUsage.id).label("request_count"),
        ).where(
            TokenUsage.user_id == user_id,
            TokenUsage.created_at >= start_date,
            TokenUsage.status == "success",
        )

        if model_type:
            query = query.where(TokenUsage.model_type == model_type)

        result = await self.db.execute(query)
        row = result.first()

        return TokenUsageStats(
            total_tokens=row.total_tokens or 0,
            input_tokens=row.input_tokens or 0,
            output_tokens=row.output_tokens or 0,
            total_cost=row.total_cost or 0.0,
            request_count=row.request_count or 0,
            period_days=days,
        )

    async def get_model_usage(
        self,
        model_config_id: int,
        days: int = 7,
    ) -> TokenUsageStats:
        """获取模型使用统计"""
        start_date = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.input_tokens).label("input_tokens"),
                func.sum(TokenUsage.output_tokens).label("output_tokens"),
                func.sum(TokenUsage.cost).label("total_cost"),
                func.count(TokenUsage.id).label("request_count"),
            ).where(
                TokenUsage.model_config_id == model_config_id,
                TokenUsage.created_at >= start_date,
                TokenUsage.status == "success",
            )
        )
        row = result.first()

        return TokenUsageStats(
            total_tokens=row.total_tokens or 0,
            input_tokens=row.input_tokens or 0,
            output_tokens=row.output_tokens or 0,
            total_cost=row.total_cost or 0.0,
            request_count=row.request_count or 0,
            period_days=days,
        )

    async def get_usage_trend(
        self,
        user_id: int,
        days: int = 30,
        model_type: Optional[str] = None,
    ) -> list[dict]:
        """获取使用趋势（按天）"""
        start_date = datetime.utcnow() - timedelta(days=days)

        query = select(
            func.date(TokenUsage.created_at).label("date"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.cost).label("cost"),
            func.count(TokenUsage.id).label("requests"),
        ).where(
            TokenUsage.user_id == user_id,
            TokenUsage.created_at >= start_date,
            TokenUsage.status == "success",
        ).group_by(func.date(TokenUsage.created_at)).order_by(func.date(TokenUsage.created_at))

        if model_type:
            query = query.where(TokenUsage.model_type == model_type)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "date": str(row.date),
                "total_tokens": row.total_tokens or 0,
                "cost": row.cost or 0.0,
                "requests": row.requests or 0,
            }
            for row in rows
        ]

    async def get_top_users(
        self,
        days: int = 7,
        limit: int = 10,
    ) -> list[dict]:
        """获取 Top 用户（按 Token 使用量）"""
        start_date = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(
                User.id,
                User.username,
                User.email,
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.cost).label("total_cost"),
                func.count(TokenUsage.id).label("request_count"),
            )
            .join(TokenUsage, TokenUsage.user_id == User.id)
            .where(
                TokenUsage.created_at >= start_date,
                TokenUsage.status == "success",
            )
            .group_by(User.id, User.username, User.email)
            .order_by(func.sum(TokenUsage.total_tokens).desc())
            .limit(limit)
        )

        return [
            {
                "user_id": row.id,
                "username": row.username,
                "email": row.email,
                "total_tokens": row.total_tokens or 0,
                "total_cost": row.total_cost or 0.0,
                "request_count": row.request_count or 0,
            }
            for row in result.all()
        ]

    async def get_quota(self, user_id: int) -> Optional[UserQuotaSchema]:
        """获取用户配额"""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()

        if not quota:
            return None

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

    async def set_quota(
        self,
        user_id: int,
        daily_token_limit: Optional[int] = None,
        daily_cost_limit: Optional[float] = None,
        monthly_token_limit: Optional[int] = None,
        monthly_cost_limit: Optional[float] = None,
        exceeded_action: str = "block",
    ) -> UserQuota:
        """设置用户配额"""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()

        if not quota:
            quota = UserQuota(
                user_id=user_id,
                daily_token_limit=daily_token_limit,
                daily_cost_limit=daily_cost_limit,
                monthly_token_limit=monthly_token_limit,
                monthly_cost_limit=monthly_cost_limit,
                exceeded_action=exceeded_action,
                daily_reset_at=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                monthly_reset_at=datetime.utcnow().replace(day=1) + timedelta(days=32),
            )
            self.db.add(quota)
        else:
            if daily_token_limit is not None:
                quota.daily_token_limit = daily_token_limit
            if daily_cost_limit is not None:
                quota.daily_cost_limit = daily_cost_limit
            if monthly_token_limit is not None:
                quota.monthly_token_limit = monthly_token_limit
            if monthly_cost_limit is not None:
                quota.monthly_cost_limit = monthly_cost_limit
            quota.exceeded_action = exceeded_action

        await self.db.commit()
        await self.db.refresh(quota)
        return quota


class QuotaService:
    """配额检查和限制服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_quota(
        self,
        user_id: int,
        requested_tokens: int = 0,
        requested_cost: float = 0.0,
    ) -> tuple[bool, str]:
        """
        检查用户配额
        Returns: (allowed, reason)
        """
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()

        if not quota or not quota.is_active:
            # No quota set, allow by default
            return True, "No quota限制"

        # Check daily limits
        if quota.daily_token_limit and quota.used_daily_tokens + requested_tokens > quota.daily_token_limit:
            return False, f"超出每日 Token 限制：{quota.used_daily_tokens}/{quota.daily_token_limit}"

        if quota.daily_cost_limit and quota.used_daily_cost + requested_cost > quota.daily_cost_limit:
            return False, f"超出每日费用限制：{quota.used_daily_cost:.2f}/{quota.daily_cost_limit:.2f}"

        # Check monthly limits
        if quota.monthly_token_limit and quota.used_monthly_tokens + requested_tokens > quota.monthly_token_limit:
            return False, f"超出每月 Token 限制：{quota.used_monthly_tokens}/{quota.monthly_token_limit}"

        if quota.monthly_cost_limit and quota.used_monthly_cost + requested_cost > quota.monthly_cost_limit:
            return False, f"超出每月费用限制：{quota.used_monthly_cost:.2f}/{quota.monthly_cost_limit:.2f}"

        return True, "配额检查通过"

    async def get_remaining_quota(self, user_id: int) -> dict:
        """获取剩余配额"""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()

        if not quota:
            return {
                "daily_tokens": None,
                "daily_cost": None,
                "monthly_tokens": None,
                "monthly_cost": None,
            }

        return {
            "daily_tokens": (quota.daily_token_limit - quota.used_daily_tokens) if quota.daily_token_limit else None,
            "daily_cost": (quota.daily_cost_limit - quota.used_daily_cost) if quota.daily_cost_limit else None,
            "monthly_tokens": (quota.monthly_token_limit - quota.used_monthly_tokens) if quota.monthly_token_limit else None,
            "monthly_cost": (quota.monthly_cost_limit - quota.used_monthly_cost) if quota.monthly_cost_limit else None,
        }