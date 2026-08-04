from __future__ import annotations
from sqlalchemy import Integer, String, Text, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from packages.core.base_model import Base, TimestampMixin, new_uuid


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    collection_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    permissions: Mapped[str] = mapped_column(String(20), default="write")
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_count: Mapped[int] = mapped_column(Integer, default=0)

    # 知识库级别的检索配置 (NULL 表示继承系统级配置)
    top_k: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    min_score: Mapped[float | None] = mapped_column(Float, default=None, nullable=True)
    enable_rerank: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)

