"""
Agent 智能体模型
支持单智能体和多智能体编排的配置管理
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, Float, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.core.base_model import Base


class AgentConfig(Base):
    """
    Agent 配置表
    支持用户创建和管理自己的智能体
    """
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 用户隔离
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 基本信息
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(500))  # 图标 URL 或 emoji

    # Agent 类型
    agent_type: Mapped[str] = mapped_column(String(20), default="single")
    # single: 单智能体
    # multi: 多智能体编排

    # 核心配置 - 运行时动态选择模型，这里只存默认配置
    default_model_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    # {provider: "anthropic", model: "claude-3-5-sonnet", temperature: 0.7}
    # 注意：实际运行时由前端传递模型配置

    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # 启用的能力
    enabled_skills: Mapped[Optional[list[str]]] = mapped_column(
        JSONB, nullable=True, default=list
    )
    # 关联 skill_skills 表的 ID 列表

    mcp_servers: Mapped[Optional[list[str]]] = mapped_column(
        JSONB, nullable=True, default=list
    )
    # 启用的 MCP 服务器配置

    # 记忆配置
    memory_type: Mapped[str] = mapped_column(String(20), default="conversation")
    # conversation: 仅对话历史
    # vector: 向量记忆 (Milvus)
    # hybrid: 混合记忆
    memory_ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    max_memory_turns: Mapped[int] = mapped_column(Integer, default=50)

    # 检索配置（关联知识库）
    kb_ids: Mapped[Optional[list[str]]] = mapped_column(
        JSONB, nullable=True, default=list
    )
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=5)
    retrieval_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # 多智能体配置（当 agent_type=multi 时）
    multi_agent_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    # {
    #   "mode": "supervisor" | "round_robin" | "custom",
    #   "workers": [
    #     {agent_id: "...", role: "researcher", ...},
    #     {agent_id: "...", role: "coder", ...}
    #   ],
    #   "supervisor_prompt": "...",
    #   "max_iterations": 10
    # }

    # 扩展配置 - 用于 LangGraph 工厂模式动态构建
    extensions_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    # {
    #   "plan_mode_enabled": false,
    #   "mcp_servers_enabled": ["server1", "server2"],
    #   "middleware_config": {...},
    #   "custom_tools": [...]
    # }

    # 安全策略（对齐 AgentManifest.security_policy）：
    # {
    #   "allowed_tools": [...],
    #   "blocked_tools": [...],
    #   "require_approval_tools": [...],
    #   "blocked_commands": [...],
    #   "max_code_execution_time_seconds": 30
    # }
    security_policy: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )

    # 沙箱策略（对齐主 Agent agent.yaml sandbox_policy，子 Agent 专属）：
    # {
    #   "timeout_seconds": 60,
    #   "max_memory_mb": 512,
    #   "network_whitelist": [...],
    #   "filesystem": {"allowed_paths": [...], "denied_paths": [...]}
    # }
    sandbox_policy: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )

    # 记忆策略（何时/如何记忆）：
    # {
    #   "type": "conversation" | "vector" | "hybrid",
    #   "max_turns": 50,
    #   "ttl_hours": 24
    # }
    memory_strategy: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft: 草稿
    # active: 已发布
    # archived: 已归档
    # disabled: 已禁用

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否分享到广场（允许其他用户查看/复制）

    # 版本
    current_version: Mapped[str] = mapped_column(String(20), default="1.0.0")

    # 使用统计
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系
    user = relationship("User", backref="agent_configs")
    versions = relationship(
        "AgentVersion",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentVersion.created_at.desc()"
    )
    memories = relationship(
        "AgentMemory",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    call_logs = relationship(
        "AgentCallLog",
        back_populates="agent",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_agent_user_status', 'user_id', 'status'),
        Index('idx_agent_tenant', 'tenant_id', 'status'),
    )

    def __repr__(self):
        return f"<AgentConfig {self.name}>"


class AgentVersion(Base):
    """
    Agent 版本管理
    每次发布新版本时保存快照
    """
    __tablename__ = "agent_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    version: Mapped[str] = mapped_column(String(20), nullable=False)
    # 语义化版本：1.0.0, 1.1.0, 2.0.0

    # 配置快照
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 保存创建时的完整配置

    # 变更说明
    changelog: Mapped[Optional[str]] = mapped_column(Text)

    # 发布者
    published_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # 关系
    agent = relationship("AgentConfig", back_populates="versions")

    __table_args__ = (
        UniqueConstraint('agent_id', 'version', name='uq_agent_version'),
        Index('idx_version_agent_created', 'agent_id', 'created_at'),
    )

    def __repr__(self):
        return f"<AgentVersion {self.version}>"


class AgentMemory(Base):
    """
    Agent 记忆存储
    支持 conversation 和 vector 两种模式
    """
    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(200), index=True)
    # 会话线程 ID，格式："{user_id}:{agent_id}:{session_id}"

    # 记忆类型
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # conversation: 对话历史
    # vector: 向量嵌入 (Milvus 中存储实际向量)
    # summary: 对话摘要

    # 记忆内容
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # conversation: {messages: [...]}
    # vector: {text: "...", embedding_ref: "milvus_id"}
    # summary: {summary: "...", keywords: []}

    # 向量引用（当 memory_type=vector 时）
    milvus_collection: Mapped[Optional[str]] = mapped_column(String(200))
    milvus_ids: Mapped[Optional[list[str]]] = mapped_column(JSONB)

    # 过期时间
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 关系
    agent = relationship("AgentConfig", back_populates="memories")
    user = relationship("User", backref="agent_memories")

    __table_args__ = (
        Index('idx_memory_user_agent_thread', 'user_id', 'agent_id', 'thread_id'),
        Index('idx_memory_expires', 'expires_at'),
    )

    def __repr__(self):
        return f"<AgentMemory {self.id}>"


class AgentCallLog(Base):
    """
    Agent 调用日志
    记录每次 Agent 执行详情
    """
    __tablename__ = "agent_call_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True, index=True
    )

    # 会话追踪
    thread_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 单次运行 ID

    # 使用的模型（运行时由用户选择）
    model_provider: Mapped[Optional[str]] = mapped_column(String(100))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))

    # Token 统计
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 性能
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    first_token_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # 状态
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # success, error, timeout, cancelled
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 输入输出摘要
    input_summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    output_summary: Mapped[Optional[dict]] = mapped_column(JSONB)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 关系
    agent = relationship("AgentConfig", back_populates="call_logs")
    user = relationship("User", backref="agent_call_logs")

    __table_args__ = (
        Index('idx_acl_agent_created', 'agent_id', 'created_at'),
        Index('idx_acl_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<AgentCallLog {self.run_id}>"
