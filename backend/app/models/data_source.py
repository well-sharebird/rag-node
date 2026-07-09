from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kb_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)

    # Sync settings
    sync_mode: Mapped[str] = mapped_column(String(20), default="manual")  # manual, scheduled, realtime, incremental
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    auto_process: Mapped[bool] = mapped_column(Boolean, default=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # active, inactive, syncing, error, pending
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sync_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Config stored as JSON for flexibility
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Flags
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="data_sources")
    sync_jobs: Mapped[list["SyncJob"]] = relationship("SyncJob", back_populates="data_source", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_ds_kb_id', 'kb_id'),
        UniqueConstraint('kb_id', 'name', name='uq_kb_data_source_name'),
    )

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


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False, index=True)

    # Job info
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, completed, failed, cancelled
    trigger_by: Mapped[str] = mapped_column(String(20), default="manual")  # manual, scheduled, api
    full_sync: Mapped[bool] = mapped_column(Boolean, default=True)

    # Progress tracking
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    data_source: Mapped["DataSource"] = relationship(back_populates="sync_jobs")
    items: Mapped[list["SyncedItem"]] = relationship("SyncedItem", back_populates="sync_job", cascade="all, delete-orphan")


class SyncedItem(Base):
    __tablename__ = "synced_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("sync_jobs.id"), nullable=False, index=True)
    data_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), nullable=False, index=True)

    __table_args__ = (
        Index('ix_synced_item_ds_ext_id', 'data_source_id', 'external_id'),
        UniqueConstraint('data_source_id', 'external_id', name='uq_source_external_id'),
    )

    # Item info
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)  # Original ID from source
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, processed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Processing
    document_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("documents.id"), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    sync_job: Mapped["SyncJob"] = relationship(back_populates="items")
    data_source: Mapped["DataSource"] = relationship()
    document: Mapped[Optional["Document"]] = relationship()  # type: ignore

    __table_args__ = (
        UniqueConstraint('data_source_id', 'external_id', name='uq_source_external_id'),
    )
