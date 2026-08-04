"""
Token Usage Schemas
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TokenUsageBase(BaseModel):
    """Token 使用基础 Schema"""
    model_name: str
    model_type: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    currency: str = "USD"
    request_type: str
    status: str = "success"


class TokenUsageCreate(TokenUsageBase):
    """创建 Token 使用记录"""
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    model_config_id: Optional[int] = None
    endpoint: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    response_id: Optional[str] = None


class TokenUsageResponse(TokenUsageBase):
    """Token 使用记录响应"""
    id: int
    user_id: Optional[int]
    api_key_id: Optional[int]
    model_config_id: Optional[int]
    endpoint: Optional[str]
    error_message: Optional[str]
    latency_ms: Optional[int]
    response_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenUsageStats(BaseModel):
    """Token 使用统计"""
    total_tokens: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    request_count: int
    period_days: int


class TokenUsageTrendItem(BaseModel):
    """使用趋势项"""
    date: str
    total_tokens: int
    cost: float
    requests: int


class UserQuotaBase(BaseModel):
    """用户配额基础"""
    daily_token_limit: Optional[int] = None
    daily_cost_limit: Optional[float] = None
    monthly_token_limit: Optional[int] = None
    monthly_cost_limit: Optional[float] = None
    exceeded_action: str = "block"


class UserQuotaSchema(UserQuotaBase):
    """用户配额响应"""
    id: int
    user_id: int
    used_daily_tokens: int
    used_daily_cost: float
    used_monthly_tokens: int
    used_monthly_cost: float
    daily_reset_at: Optional[datetime]
    monthly_reset_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class UserQuotaUpdate(BaseModel):
    """更新用户配额"""
    daily_token_limit: Optional[int] = None
    daily_cost_limit: Optional[float] = None
    monthly_token_limit: Optional[int] = None
    monthly_cost_limit: Optional[float] = None
    is_active: Optional[bool] = None
    exceeded_action: Optional[str] = None


class ModelProviderBase(BaseModel):
    """模型供应商基础"""
    name: str
    display_name: str
    provider_type: str  # api, local
    category: str = "llm"
    api_base: Optional[str] = None
    auth_type: Optional[str] = None
    pricing: Optional[dict] = None
    capabilities: Optional[list[str]] = None
    icon: Optional[str] = None
    description: Optional[str] = None


class ModelProviderCreate(ModelProviderBase):
    """创建供应商"""
    pass


class ModelProviderResponse(ModelProviderBase):
    """供应商响应"""
    id: int
    is_enabled: bool
    is_default: bool
    supported_models: Optional[list[str]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    """仪表盘统计"""
    total_users: int
    total_tokens_today: int
    total_tokens_month: int
    total_cost_today: float
    total_cost_month: float
    active_models: int
    requests_today: int
