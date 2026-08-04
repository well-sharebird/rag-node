"""
模型网关数据库模型
支持供应商管理、路由规则、监控日志
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, Float, ForeignKey,
    UniqueConstraint, Index, Numeric
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.core.base_model import Base


class ModelProvider(Base):
    """
    模型供应商配置
    支持国内外主流 LLM 云供应商
    """
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 供应商类型
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # cloud: OpenAI, Anthropic, Google, Azure, AWS
    # domestic: 智谱，月之暗面，阿里云，百川
    # self_hosted: Ollama, vLLM, Triton

    # 区域
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # international, china, us-east, ap-southeast, etc.

    # API 配置
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Azure OpenAI 需要 api-version 参数

    # 认证配置
    auth_type: Mapped[str] = mapped_column(String(50), default="api_key")
    # api_key, oauth, aws_sigv4, azure_ad
    api_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    api_key_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 请求头中的 API Key 名称，如 X-API-Key, Authorization

    # 额外配置 (JSON)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # 状态
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, inactive, error, rate_limited

    # 健康检查
    health_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    # 速率限制配置
    rate_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_requests: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 每分钟请求数限制
    rate_limit_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 每分钟 Token 数限制

    # 成本配置 (每 1K tokens)
    cost_input: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    cost_output: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)

    # 元数据
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    routing_rules = relationship(
        "ModelRoutingRule",
        back_populates="provider",
        cascade="all, delete-orphan",
        foreign_keys="ModelRoutingRule.provider_id"
    )
    # Note: model_configs relationship removed - ModelConfig.provider is a string field, not a ForeignKey
    call_logs = relationship("ModelCallLog", back_populates="provider")

    def __repr__(self):
        return f"<ModelProvider {self.name} ({self.code})>"


class ModelRoutingRule(Base):
    """
    模型路由规则
    定义请求如何路由到不同的供应商
    """
    __tablename__ = "model_routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 规则基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 关联供应商
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("model_providers.id"), nullable=False
    )

    # 路由条件
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # llm, embedding, rerank, vision, speech_to_text, text_to_speech

    priority: Mapped[int] = mapped_column(Integer, default=100)
    # 优先级，数字越小优先级越高

    # 路由匹配条件 (JSON)
    # 示例：{"models": ["gpt-4", "gpt-4-turbo"], "users": ["admin"], "tags": ["premium"]}
    match_conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # 流量分配 (0-100)
    traffic_weight: Mapped[int] = mapped_column(Integer, default=100)
    # 用于 A/B 测试或灰度发布

    # 故障转移配置
    failover_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failover_provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("model_providers.id"), nullable=True
    )
    # 故障时转移到的供应商

    failover_threshold: Mapped[int] = mapped_column(Integer, default=3)
    # 连续失败多少次后触发故障转移

    failover_window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    # 故障判断时间窗口

    # 超时配置
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)

    # 重试配置
    retry_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_delay_ms: Mapped[int] = mapped_column(Integer, default=1000)

    # 状态
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    provider = relationship(
        "ModelProvider",
        back_populates="routing_rules",
        foreign_keys=[provider_id]
    )
    failover_provider = relationship(
        "ModelProvider",
        foreign_keys=[failover_provider_id],
        remote_side="ModelProvider.id"
    )

    __table_args__ = (
        Index('idx_routing_type_priority', 'model_type', 'priority'),
    )

    def __repr__(self):
        return f"<ModelRoutingRule {self.name}>"


class ModelCallLog(Base):
    """
    模型调用日志
    记录每次模型调用的详细信息
    """
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 请求信息
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, unique=True)
    # 唯一请求 ID

    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("model_providers.id"), nullable=False, index=True
    )

    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # 用户/应用信息
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    app_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    kb_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # 请求参数
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 性能指标
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 请求延迟 (毫秒)

    first_token_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 首 Token 延迟 (流式调用)

    # 响应状态
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # success, error, timeout, rate_limited

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 成本计算
    cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    # 本次调用成本 (美元)

    # 缓存信息
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否命中缓存

    # 原始请求/响应 (可选存储)
    request_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # 关系
    provider = relationship("ModelProvider", back_populates="call_logs")

    __table_args__ = (
        Index('idx_mcl_provider_created', 'provider_id', 'created_at'),
        Index('idx_mcl_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<ModelCallLog {self.request_id}>"


class ModelCache(Base):
    """
    模型响应缓存
    避免重复计算，节省成本
    """
    __tablename__ = "model_caches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 缓存键
    cache_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    # 基于请求内容的哈希

    # 缓存内容
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)

    response_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 缓存的响应数据

    # 缓存元数据
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 原始调用的延迟

    # 缓存策略
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # 命中统计
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_cache_expires', 'expires_at'),
    )

    def __repr__(self):
        return f"<ModelCache {self.cache_key}>"
