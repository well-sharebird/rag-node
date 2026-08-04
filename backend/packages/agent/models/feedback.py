"""
Feedback model - 问答反馈数据模型
"""
from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from packages.core.base_model import Base, TimestampMixin, new_uuid


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # 关联信息
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # 反馈类型
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # thumbs_up, thumbs_down
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 分

    # 反馈原因（点踩时）
    reason_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 原因选项：
    # - irrelevant: 与问题无关
    # - incorrect: 信息错误
    # - incomplete: 信息不完整
    # - outdated: 信息过时
    # - harmful: 有害内容
    # - other: 其他

    reason_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 用户自由填写的原因

    # 额外反馈
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 上下文快照
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referenced_docs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of doc_ids

    # 元数据
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    kb_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # 处理状态
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # 有用性评分（用于排序）
    helpfulness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    @property
    def is_positive(self) -> bool:
        return self.feedback_type == "thumbs_up"

    @property
    def is_negative(self) -> bool:
        return self.feedback_type == "thumbs_down"
