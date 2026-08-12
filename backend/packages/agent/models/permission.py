"""权限审批请求 - DB 持久化模型（HITL 人工审批闭环）
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from packages.core.base_model import Base


class PermissionRequest(Base):
    """人工审批请求（敏感工具 require_approval 时产生）"""
    __tablename__ = "permission_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False, default="execute")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    permission_level: Mapped[str] = mapped_column(String(30), nullable=False, default="approve_once")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    requester_id: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[int] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
