"""
Workspace 工作区模型

用户工作区提供文件隔离机制，确保：
1. 用户 A 无法访问用户 B 的文件
2. 代码执行限定在用户工作区内
3. 文件访问可审计追踪
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


class Workspace(Base):
    """
    用户工作区

    每个用户拥有独立的工作区，用于存储：
    - Session 相关文件
    - 知识库文件
    - Agent 配置
    - 代码执行输出
    """
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 用户关联
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 工作区根路径 (文件系统路径)
    root_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    # 示例：/workspace/users/123/

    # 存储配额
    storage_quota_bytes: Mapped[int] = mapped_column(
        BigInteger, default=10 * 1024 * 1024 * 1024  # 默认 10GB
    )
    storage_used_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0
    )

    # 状态
    status: Mapped[str] = mapped_column(
        String(20), default="active", index=True
    )
    # active: 正常
    # suspended: 暂停 (配额超限或违规)
    # deleted: 已删除

    # 安全标记
    is_isolated: Mapped[bool] = mapped_column(
        Boolean, default=True
    )
    # True = 严格隔离模式，禁止跨工作区访问

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    user = relationship("User", backref="workspaces")
    files = relationship(
        "WorkspaceFile",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )
    runtimes = relationship(
        "AgentRuntime",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    # 索引
    __table_args__ = (
        Index('idx_workspace_user_tenant', 'user_id', 'tenant_id'),
        Index('idx_workspace_status', 'status'),
    )

    def __repr__(self):
        return f"<Workspace user_id={self.user_id} path={self.root_path}>"

    @property
    def is_active(self) -> bool:
        """检查工作区是否可用"""
        return self.status == "active"

    @property
    def storage_used_percent(self) -> float:
        """计算存储使用百分比"""
        if self.storage_quota_bytes == 0:
            return 0.0
        return (self.storage_used_bytes / self.storage_quota_bytes) * 100

    def check_quota(self, required_bytes: int) -> bool:
        """检查是否有足够配额"""
        return (self.storage_used_bytes + required_bytes) <= self.storage_quota_bytes


class WorkspaceFile(Base):
    """
    工作区文件索引

    记录工作区中的文件，用于：
    1. 配额统计
    2. 安全审计
    3. 文件溯源
    """
    __tablename__ = "workspace_files"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 关联
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 可选：关联到特定 Runtime/Session
    runtime_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtimes.id", ondelete="SET NULL"),
        nullable=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # 文件信息
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    # 相对于 workspace 根目录的路径

    absolute_path: Mapped[Optional[str]] = mapped_column(String(1000))
    # 缓存的绝对路径

    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(200))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    # SHA-256 哈希

    # 来源标记
    source_type: Mapped[str] = mapped_column(
        String(20), default="upload"
    )
    # upload: 用户上传
    # generated: 代码生成
    # downloaded: 外部下载

    is_sandbox_generated: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    # 是否由沙箱代码生成

    # 安全扫描
    scan_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )
    # pending: 待扫描
    # scanning: 扫描中
    # clean: 安全
    # malicious: 恶意
    # error: 扫描失败

    scan_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # 扫描结果详情

    # 元数据
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    workspace = relationship("Workspace", back_populates="files")

    # 索引和约束
    __table_args__ = (
        UniqueConstraint(
            'workspace_id', 'relative_path',
            name='uq_workspace_file_path'
        ),
        Index('idx_file_workspace_created', 'workspace_id', 'created_at'),
        Index('idx_file_scan_status', 'scan_status'),
    )

    def __repr__(self):
        return f"<WorkspaceFile {self.filename}>"


class WorkspaceAuditLog(Base):
    """
    工作区审计日志

    记录所有文件访问和操作
    """
    __tablename__ = "workspace_audit_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # 关联
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    runtime_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtimes.id", ondelete="SET NULL"),
        nullable=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100))

    # 操作信息
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # read, write, delete, execute, download, upload

    # 文件信息
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)

    # 操作结果
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 上下文
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # 索引
    __table_args__ = (
        Index('idx_audit_workspace_action', 'workspace_id', 'action'),
        Index('idx_audit_workspace_created', 'workspace_id', 'created_at'),
        Index('idx_audit_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<WorkspaceAuditLog {self.action} {self.file_path}>"
