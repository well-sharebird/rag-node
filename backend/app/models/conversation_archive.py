"""
会话归档模型
支持会话历史的分层存储（热/温/冷数据）
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, Float, ForeignKey,
    UniqueConstraint, Index, BigInteger
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ConversationArchive(Base):
    """
    会话归档表 - 用于存储过期会话的归档记录

    归档策略：
    - 热数据：0-7 天，存储在 agent_memories 表
    - 温数据：7-30 天，压缩后存储在此表
    - 冷数据：30 天以上，存储到 MinIO/S3，此表只存元数据
    """
    __tablename__ = "conversation_archives"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 用户隔离
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # 关联信息
    thread_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # 会话线程 ID，格式："{user_id}:{agent_id}:{session_id}"

    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    # agent_id 可能为 NULL（如果关联的 agent 被删除）

    agent_name: Mapped[str] = mapped_column(String(200), nullable=True)
    # 冗余存储 agent 名称，避免关联查询

    # 归档类型
    archive_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    # warm: 温数据（压缩存储在 DB）
    # cold: 冷数据（存储在 MinIO/S3）

    # 归档内容
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    # 消息总数

    compressed_content: Mapped[Optional[bytes]] = mapped_column(
        nullable=True
    )
    # 压缩后的对话内容（仅 warm 类型使用）
    # 格式：gzip 压缩的 JSONL

    archive_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # MinIO/S3 路径（仅 cold 类型使用）
    # 格式：archives/{user_id}/{thread_id}_{date}.jsonl.gz

    archive_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    # 归档文件大小（字节）

    # 时间范围
    date_range_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # 归档数据的起始日期

    date_range_end: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # 归档数据的结束日期

    # 智能摘要（用于快速预览）
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # LLM 生成的会话摘要（200 字以内）

    keywords: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    # 关键词提取，用于搜索

    # 最后消息预览
    last_message_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 最后一条消息的预览（前 100 字）

    last_message_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # 最后一条消息的时间

    # 状态
    is_restored: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否已恢复到热存储

    # 时间戳
    archived_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    # 归档时间

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 过期时间（冷数据可设置更长的保留期）

    # 关系
    user = relationship("User", backref="conversation_archives")
    agent = relationship("AgentConfig", backref="conversation_archives")

    __table_args__ = (
        Index('idx_archive_user_thread', 'user_id', 'thread_id'),
        Index('idx_archive_user_date', 'user_id', 'date_range_end'),
        Index('idx_archive_tier', 'archive_tier', 'archived_at'),
    )

    def __repr__(self):
        return f"<ConversationArchive {self.thread_id} @{self.archive_tier}>"


class ConversationArchiveConfig(Base):
    """
    会话归档配置表

    允许管理员自定义归档策略
    """
    __tablename__ = "conversation_archive_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 配置名称
    config_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # 归档策略
    hot_tier_days: Mapped[int] = mapped_column(Integer, default=7)
    # 热数据保留天数

    warm_tier_days: Mapped[int] = mapped_column(Integer, default=30)
    # 温数据保留天数（超过此天数进入冷存储）

    cold_tier_days: Mapped[int] = mapped_column(Integer, default=365)
    # 冷数据保留天数（超过此天数可删除）

    # 归档触发条件
    archive_batch_size: Mapped[int] = mapped_column(Integer, default=100)
    # 每次归档的最大会话数

    min_message_count: Mapped[int] = mapped_column(Integer, default=5)
    # 最小消息数（少于这个消息数的会话不归档）

    # 压缩配置
    compression_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    compression_level: Mapped[int] = mapped_column(Integer, default=6)
    # gzip 压缩级别 1-9

    # MinIO/S3 配置
    minio_bucket: Mapped[str] = mapped_column(String(100), default="conversation-archives")
    minio_prefix: Mapped[str] = mapped_column(String(200), default="archives")

    # 状态
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<ConversationArchiveConfig {self.config_name}>"
