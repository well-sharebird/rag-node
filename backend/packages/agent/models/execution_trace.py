"""
Execution Trace 执行追踪模型

用于记录和追踪 Harness Engine 的执行过程，支持：
- 执行历史查询
- 性能分析
- 错误调试
- 审计日志
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import uuid

from packages.core.base_model import Base


class ExecutionTrace(Base):
    """
    执行追踪表

    记录每次 Harness Engine 执行的完整链路
    """
    __tablename__ = "execution_traces"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 执行标识
    run_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, unique=True)
    thread_id: Mapped[str] = mapped_column(String(200), nullable=True, index=True)

    # 用户/租户标识
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)

    # Agent 信息
    agent_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(200), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=True)  # single, multi, meta

    # 意图分析
    intent_type: Mapped[str] = mapped_column(String(50), nullable=True)  # specified, agent, default, general

    # 执行状态
    status: Mapped[str] = mapped_column(String(50), default="success", index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # 性能指标
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 执行步骤 (JSON 数组)
    steps: Mapped[dict] = mapped_column(JSONB, default=list)

    # 工具调用记录
    tool_calls: Mapped[dict] = mapped_column(JSONB, default=list)

    # 输入输出摘要
    input_summary: Mapped[str] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 索引
    __table_args__ = (
        Index("ix_execution_traces_user_created", "user_id", "created_at"),
        Index("ix_execution_traces_agent_created", "agent_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "intent_type": self.intent_type,
            "status": self.status,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "steps": self.steps or [],
            "tool_calls": self.tool_calls or [],
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
