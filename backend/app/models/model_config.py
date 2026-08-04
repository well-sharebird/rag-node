from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Text, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # llm, embedding, rerank, etc.
    adapter_type: Mapped[str] = mapped_column(String(50), nullable=False)  # local, api, ollama, vllm
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Model parameters (stored as JSON for flexibility)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    top_p: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency_penalty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    presence_penalty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Embedding specific
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    normalization: Mapped[bool] = mapped_column(Boolean, default=True)

    # Runtime
    batch_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="inactive")  # active, inactive, error
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Flags
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('model_type', 'name', name='uq_model_type_name'),
    )

    # Relationships
    token_usages = relationship("TokenUsage", back_populates="model_config")

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
        self.tags = json.dumps(value)
