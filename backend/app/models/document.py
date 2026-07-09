from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    minio_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Category & Tags
    category: Mapped[str] = mapped_column(String(200), default="", index=True)  # e.g., "/产品/手册/部署"
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array, e.g., '["v1.0","部署","安全"]'

    # Version tracking
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def tags_list(self) -> list[str]:
        import json
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []

    @tags_list.setter
    def tags_list(self, value: list[str]):
        import json
        self.tags = json.dumps(value) if value else None
