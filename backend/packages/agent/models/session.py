"""
Agent Session 会话模型

Session 代表用户与 Agent 的一次完整交互过程
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.core.base_model import Base


class AgentSession(Base):
    """
    Agent 会话实例

    每个 Session 代表用户与 Agent 的一次完整交互过程
    """
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    runtime_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtimes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 会话令牌 (安全)
    session_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    # SHA-256 哈希的会话令牌

    session_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 会话元数据
    name: Mapped[Optional[str]] = mapped_column(String(200))
    # 可选的会话名称，用户可自定义

    # 上下文管理
    context_window_tokens: Mapped[int] = mapped_column(
        Integer, default=4096
    )
    # 上下文窗口大小

    context_used_tokens: Mapped[int] = mapped_column(
        Integer, default=0
    )
    # 已使用的 token 数

    # 状态
    status: Mapped[str] = mapped_column(
        String(20), default="active", index=True
    )
    # active: 活跃
    # idle: 空闲
    # archived: 已归档
    # expired: 已过期

    # 最后活动时间
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, index=True
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 关系
    runtime = relationship("AgentRuntime", back_populates="sessions")
    user = relationship("User", backref="agent_sessions")
    messages = relationship(
        "AgentSessionMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentSessionMessage.created_at"
    )
    events = relationship(
        "AgentEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentEvent.seq"
    )

    # 索引
    __table_args__ = (
        Index('idx_session_user_runtime', 'user_id', 'runtime_id'),
        Index('idx_session_token', 'session_token_hash'),
        Index('idx_session_status_activity', 'status', 'last_activity_at'),
    )

    def __repr__(self):
        return f"<AgentSession {self.id}>"

    @property
    def is_active(self) -> bool:
        """检查会话是否活跃"""
        return self.status == "active"

    def update_activity(self):
        """更新活动时间"""
        self.last_activity_at = datetime.utcnow()


class AgentSessionMessage(Base):
    """
    会话消息

    记录用户与 Agent 的对话内容
    """
    __tablename__ = "agent_session_messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 消息角色
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    # system: 系统提示
    # user: 用户输入
    # assistant: Agent 回复
    # tool: 工具调用结果

    # 消息内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(20), default="text"
    )
    # text: 纯文本
    # markdown: Markdown 格式
    # code: 代码块
    # json: JSON 数据

    # 工具调用信息 (当 role=assistant 且有工具调用时)
    tool_calls: Mapped[Optional[list[dict]]] = mapped_column(JSONB)
    # [
    #   {
    #     "id": "call_123",
    #     "name": "code_interpreter",
    #     "arguments": {"code": "print('hello')"},
    #     "result": "hello"
    #   }
    # ]

    # 资源引用
    referenced_file_ids: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    # 引用的文件 ID 列表

    # Token 统计
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # 执行追踪
    run_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    # 单次运行 ID，用于追踪

    trace_id: Mapped[Optional[str]] = mapped_column(String(100))
    # 全链路追踪 ID

    # 状态
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 关系
    session = relationship("AgentSession", back_populates="messages")

    # 索引
    __table_args__ = (
        Index('idx_message_session_created', 'session_id', 'created_at'),
        Index('idx_message_role_created', 'role', 'created_at'),
        Index('idx_message_run_id', 'run_id'),
    )

    def __repr__(self):
        return f"<AgentSessionMessage {self.role}>"


class AgentSessionCheckpoint(Base):
    """
    会话检查点

    用于保存会话状态，支持断点续传和恢复
    """
    __tablename__ = "agent_session_checkpoints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 检查点名称
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # 检查点数据
    checkpoint_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # {
    #   "messages": [...],
    #   "context": {...},
    #   "variables": {...}
    # }

    # 检查点类型
    checkpoint_type: Mapped[str] = mapped_column(
        String(20), default="manual"
    )
    # manual: 手动创建
    # auto: 自动创建
    # system: 系统创建

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 关系
    session = relationship("AgentSession", backref="checkpoints")

    # 索引
    __table_args__ = (
        Index('idx_checkpoint_session_created', 'session_id', 'created_at'),
        Index('idx_checkpoint_type', 'checkpoint_type'),
    )

    def __repr__(self):
        return f"<AgentSessionCheckpoint {self.name}>"
