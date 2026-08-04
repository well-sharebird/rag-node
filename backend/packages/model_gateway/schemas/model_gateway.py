"""
模型网关 Pydantic Schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


# ========== 供应商 Schemas ==========

class ModelProviderBase(BaseModel):
    """供应商基础 Schema"""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="供应商 ID")
    name: str = Field(..., description="供应商名称", max_length=100)
    code: str = Field(..., description="供应商代码", max_length=50)
    description: Optional[str] = Field(None, description="描述")
    provider_type: str = Field(..., description="供应商类型", max_length=50)
    region: Optional[str] = Field(None, description="区域", max_length=100)
    base_url: str = Field(..., description="API 基础 URL", max_length=500)
    api_version: Optional[str] = Field(None, description="API 版本", max_length=50)
    auth_type: str = Field(default="api_key", description="认证类型", max_length=50)
    api_key_name: Optional[str] = Field(None, description="API Key 名称", max_length=100)
    api_key: Optional[str] = Field(None, description="API Key", max_length=1000)
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外配置")
    is_enabled: bool = Field(default=True, description="是否启用")
    status: str = Field(default="active", description="状态", max_length=20)
    health_status: Optional[str] = Field(None, description="健康状态")
    last_health_check: Optional[datetime] = Field(None, description="最后健康检查时间")
    consecutive_failures: int = Field(default=0, description="连续失败次数")
    rate_limit_enabled: bool = Field(default=False, description="是否启用速率限制")
    rate_limit_requests: Optional[int] = Field(None, description="每分钟请求数限制")
    rate_limit_tokens: Optional[int] = Field(None, description="每分钟 Token 数限制")
    cost_input: Optional[float] = Field(None, description="输入成本 (每 1K tokens)", ge=0)
    cost_output: Optional[float] = Field(None, description="输出成本 (每 1K tokens)", ge=0)
    tags: Optional[str] = Field(None, description="标签 (JSON 数组)")
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ModelProviderCreate(BaseModel):
    """创建供应商 Schema"""
    name: str = Field(..., description="供应商名称", max_length=100)
    code: str = Field(..., description="供应商代码", max_length=50)
    description: Optional[str] = Field(None, description="描述")
    provider_type: str = Field(..., description="供应商类型", max_length=50)
    region: Optional[str] = Field(None, description="区域", max_length=100)
    base_url: str = Field(..., description="API 基础 URL", max_length=500)
    api_version: Optional[str] = Field(None, description="API 版本", max_length=50)
    auth_type: str = Field(default="api_key", description="认证类型", max_length=50)
    api_key_name: Optional[str] = Field(None, description="API Key 名称", max_length=100)
    api_key: Optional[str] = Field(None, description="API Key", max_length=1000)
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外配置")
    is_enabled: bool = Field(default=True, description="是否启用")
    status: str = Field(default="active", description="状态", max_length=20)
    rate_limit_enabled: bool = Field(default=False, description="是否启用速率限制")
    rate_limit_requests: Optional[int] = Field(None, description="每分钟请求数限制")
    rate_limit_tokens: Optional[int] = Field(None, description="每分钟 Token 数限制")
    cost_input: Optional[float] = Field(None, description="输入成本 (每 1K tokens)", ge=0)
    cost_output: Optional[float] = Field(None, description="输出成本 (每 1K tokens)", ge=0)
    tags: Optional[str] = Field(None, description="标签 (JSON 数组)")
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")


class ModelProviderUpdate(BaseModel):
    """更新供应商 Schema"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    provider_type: Optional[str] = Field(None, max_length=50)
    region: Optional[str] = Field(None, max_length=100)
    base_url: Optional[str] = Field(None, max_length=500)
    api_version: Optional[str] = Field(None, max_length=50)
    auth_type: Optional[str] = Field(None, max_length=50)
    api_key_name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, max_length=1000)
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    status: Optional[str] = Field(None, max_length=20)
    rate_limit_enabled: Optional[bool] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_tokens: Optional[int] = None
    cost_input: Optional[float] = Field(None, ge=0)
    cost_output: Optional[float] = Field(None, ge=0)
    tags: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class ModelProviderResponse(BaseModel):
    """供应商响应 Schema"""
    item: ModelProviderBase


class ModelProviderListResponse(BaseModel):
    """供应商列表响应 Schema"""
    items: List[ModelProviderBase]
    total: int


# ========== 路由规则 Schemas ==========

class ModelRoutingRuleBase(BaseModel):
    """路由规则基础 Schema"""
    name: str = Field(..., description="规则名称", max_length=100)
    description: Optional[str] = Field(None, description="描述")
    provider_id: int = Field(..., description="供应商 ID")
    model_type: str = Field(..., description="模型类型", max_length=50)
    priority: int = Field(default=100, description="优先级", ge=1)
    match_conditions: Optional[Dict[str, Any]] = Field(default_factory=dict, description="匹配条件")
    traffic_weight: int = Field(default=100, description="流量权重", ge=0, le=100)
    failover_enabled: bool = Field(default=False, description="是否启用故障转移")
    failover_provider_id: Optional[int] = Field(None, description="故障转移供应商 ID")
    failover_threshold: int = Field(default=3, description="故障转移阈值", ge=1)
    failover_window_seconds: int = Field(default=60, description="故障判断时间窗口", ge=1)
    timeout_ms: int = Field(default=30000, description="超时时间 (ms)", ge=1000)
    retry_enabled: bool = Field(default=False, description="是否启用重试")
    retry_max_attempts: int = Field(default=3, description="最大重试次数", ge=1)
    retry_delay_ms: int = Field(default=1000, description="重试延迟 (ms)", ge=100)
    is_enabled: bool = Field(default=True, description="是否启用")


class ModelRoutingRuleCreate(ModelRoutingRuleBase):
    """创建路由规则 Schema"""
    pass


class ModelRoutingRuleUpdate(BaseModel):
    """更新路由规则 Schema"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    provider_id: Optional[int] = None
    model_type: Optional[str] = Field(None, max_length=50)
    priority: Optional[int] = Field(None, ge=1)
    match_conditions: Optional[Dict[str, Any]] = None
    traffic_weight: Optional[int] = Field(None, ge=0, le=100)
    failover_enabled: Optional[bool] = None
    failover_provider_id: Optional[int] = None
    failover_threshold: Optional[int] = Field(None, ge=1)
    failover_window_seconds: Optional[int] = Field(None, ge=1)
    timeout_ms: Optional[int] = Field(None, ge=1000)
    retry_enabled: Optional[bool] = None
    retry_max_attempts: Optional[int] = Field(None, ge=1)
    retry_delay_ms: Optional[int] = Field(None, ge=100)
    is_enabled: Optional[bool] = None


class ModelRoutingRuleResponse(ModelRoutingRuleBase):
    """路由规则响应 Schema"""
    model_config = ConfigDict(from_attributes=True)

    item: ModelRoutingRuleBase


class ModelRoutingRuleListResponse(BaseModel):
    """路由规则列表响应 Schema"""
    items: List[ModelRoutingRuleBase]
    total: int


# ========== 调用日志 Schemas ==========

class ModelCallLogBase(BaseModel):
    """调用日志基础 Schema"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    provider_id: int
    model_id: str
    model_type: str
    user_id: Optional[int] = None
    app_id: Optional[str] = None
    kb_id: Optional[str] = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    first_token_latency_ms: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    cost: Optional[float] = None
    cached: bool
    created_at: datetime


class ModelCallLogResponse(BaseModel):
    """调用日志响应 Schema"""
    item: ModelCallLogBase


class ModelCallLogListResponse(BaseModel):
    """调用日志列表响应 Schema"""
    items: List[ModelCallLogBase]
    total: int


class ModelCallStatistics(BaseModel):
    """调用统计 Schema"""
    total_calls: int
    success_calls: int
    error_calls: int
    success_rate: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: float
    avg_latency_ms: float
    cache_hits: int
    cache_hit_rate: float


# ========== 缓存 Schemas ==========

class ModelCacheStatistics(BaseModel):
    """缓存统计 Schema"""
    total_caches: int
    expiring_caches: int
    total_hits: int
