"""
Conversation model - 对话历史数据模型
"""
from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # 用户关联 (users.id is Integer)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 会话信息
    title: Mapped[str] = mapped_column(String(200), nullable=True)  # 自动生成或用户自定义
    kb_ids: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # JSON array of kb_ids

    # 会话状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # 消息计数
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 元数据
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON metadata

    def __repr__(self) -> str:
        return f"<Conversation {self.id} title={self.title}>"


class ConversationMessage(Base, TimestampMixin):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # 关联
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)

    # 消息内容
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 引用来源
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of citations

    # 元数据
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 排序
    message_index: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<ConversationMessage {self.id} conv={self.conversation_id} role={self.role}>"
