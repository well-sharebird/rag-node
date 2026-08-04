"""
Token Usage Tracking Models
用于记录和分析 Token 使用情况
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Float, Text, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from packages.core.base_model import Base


class TokenUsage(Base):
    """Token 使用记录"""
    __tablename__ = "token_usages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # User and model info
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    model_config_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True, index=True)

    # Model info (denormalized for faster queries)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # llm, embedding, rerank
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Token counts
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Cost (in USD or CNY)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Request info
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)  # chat, completion, embedding, rerank
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, error, rate_limited

    # Error info
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Response metadata
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="token_usages")
    api_key = relationship("APIKey", back_populates="token_usages")
    model_config = relationship("ModelConfig", back_populates="token_usages")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_token_usage_user_date", "user_id", "created_at"),
        Index("idx_token_usage_model_date", "model_config_id", "created_at"),
    )


class UserQuota(Base):
    """用户 Token 配额"""
    __tablename__ = "user_quotas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Daily limits
    daily_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Total tokens per day
    daily_cost_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # Cost limit per day

    # Monthly limits
    monthly_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_cost_limit: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Model-specific limits (JSON format)
    # {"llm": {"daily_tokens": 10000, "monthly_tokens": 100000}, "embedding": {...}}
    model_limits: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Current usage (reset at midnight)
    used_daily_tokens: Mapped[int] = mapped_column(Integer, default=0)
    used_daily_cost: Mapped[float] = mapped_column(Float, default=0.0)
    used_monthly_tokens: Mapped[int] = mapped_column(Integer, default=0)
    used_monthly_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # Reset timestamps
    daily_reset_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    monthly_reset_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    exceeded_action: Mapped[str] = mapped_column(String(20), default="block")  # block, warn, log

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="quota")


# Note: ModelProvider is now defined in app.models.model_gateway
# This file only contains TokenUsage and UserQuota models
