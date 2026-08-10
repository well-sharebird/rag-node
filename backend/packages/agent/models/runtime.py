"""
Agent Runtime 运行时模型

Runtime 是 Agent 的独立运行环境，包含：
- 沙箱实例 (Firecracker VM 或 nsjail 容器)
- Manifest 配置
- 一个或多个 Session
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


class AgentRuntime(Base):
    """
    Agent 运行时实例

    每个 Runtime 代表一个独立的 Agent 运行环境
    """
    __tablename__ = "agent_runtimes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Manifest (声明式配置)
    manifest: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    # {
    #   "agent_id": "...",
    #   "name": "...",
    #   "version": "1.0.0",
    #   "model_config": {...},
    #   "system_prompt": "...",
    #   "enabled_tools": [...],
    #   "workspace": {...},
    #   "security_policy": {...}
    # }

    # 沙箱配置
    sandbox_type: Mapped[str] = mapped_column(
        String(20), default="nsjail"
    )
    # nsjail: 轻量级隔离
    # firecracker: MicroVM 完全隔离
    # docker: 容器隔离
    # process: 进程隔离 (开发模式，不安全)

    sandbox_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    # 沙箱实例 ID (VM ID 或容器 ID)

    sandbox_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # 沙箱具体配置
    # {
    #   "memory_mb": 128,
    #   "vcpu_count": 1,
    #   "timeout_seconds": 30,
    #   "network_enabled": false,
    #   ...
    # }

    # 状态
    status: Mapped[str] = mapped_column(
        String(20), default="initializing", index=True
    )
    # initializing: 初始化中
    # running: 运行中
    # sleeping: 休眠中 (自动休眠节省资源)
    # stopped: 已停止
    # failed: 启动失败
    # error: 错误状态

    # 资源使用统计
    resource_usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {
    #   "cpu_percent": 10.5,
    #   "memory_mb": 128,
    #   "disk_mb": 50,
    #   "last_updated": "2026-08-05T10:00:00Z"
    # }

    # 生命周期管理
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, index=True
    )
    idle_timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=900
    )  # 15 分钟空闲后休眠
    auto_sleep_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    # 启动次数 (用于统计和预热池管理)
    start_count: Mapped[int] = mapped_column(Integer, default=0)
    last_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 关系
    sessions = relationship(
        "AgentSession",
        back_populates="runtime",
        cascade="all, delete-orphan"
    )
    agent = relationship("AgentConfig")
    workspace = relationship("Workspace", back_populates="runtimes")
    creator = relationship("User", foreign_keys=[created_by])

    # 文件关联 (只读，不配置 back_populates)
    files = relationship(
        "WorkspaceFile",
        primaryjoin="and_(WorkspaceFile.runtime_id==AgentRuntime.id, WorkspaceFile.workspace_id==AgentRuntime.workspace_id)",
        viewonly=True,
    )

    # 索引
    __table_args__ = (
        Index('idx_runtime_agent_status', 'agent_id', 'status'),
        Index('idx_runtime_workspace_status', 'workspace_id', 'status'),
        Index('idx_runtime_sandbox', 'sandbox_id'),
        Index('idx_runtime_last_active', 'last_active_at'),
    )

    def __repr__(self):
        return f"<AgentRuntime {self.id} agent={self.agent_id}>"

    @property
    def is_running(self) -> bool:
        """检查是否在运行"""
        return self.status == "running"

    @property
    def is_sleeping(self) -> bool:
        """检查是否在休眠"""
        return self.status == "sleeping"

    @property
    def idle_seconds(self) -> Optional[int]:
        """计算空闲秒数"""
        if self.last_active_at:
            delta = datetime.utcnow() - self.last_active_at
            return int(delta.total_seconds())
        return None

    def should_sleep(self) -> bool:
        """判断是否应该进入休眠"""
        if not self.auto_sleep_enabled:
            return False
        if self.status != "running":
            return False
        idle = self.idle_seconds
        return idle is not None and idle >= self.idle_timeout_seconds


class AgentRuntimeEvent(Base):
    """
    Runtime 事件日志

    记录 Runtime 生命周期中的重要事件
    """
    __tablename__ = "agent_runtime_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # 关联
    runtime_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtimes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 事件类型
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # created, started, stopped, slept, woken, error, resource_update

    # 事件详情
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    # {
    #   "reason": "...",
    #   "error_message": "...",
    #   "resource_before": {...},
    #   "resource_after": {...}
    # }

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 索引
    __table_args__ = (
        Index('idx_event_runtime_created', 'runtime_id', 'created_at'),
        Index('idx_event_type_created', 'event_type', 'created_at'),
    )

    def __repr__(self):
        return f"<AgentRuntimeEvent {self.event_type}>"
