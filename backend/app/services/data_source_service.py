from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource, SyncJob, SyncedItem
from app.schemas.data_source import (
    DataSourceCreate, DataSourceUpdate, DataSourceResponse,
    DataSourceType, SyncMode, DataSourceStatus, SyncJobStatus
)

logger = logging.getLogger("app.services.data_source")


# ============================================================
# Data Source CRUD
# ============================================================

async def list_data_sources(
    db: AsyncSession,
    kb_id: Optional[str] = None,  # Changed to str to match UUID format
    source_type: Optional[str] = None,
    enabled_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[DataSource], int]:
    """List data sources with pagination"""
    stmt = select(DataSource).order_by(DataSource.created_at.desc())

    if kb_id:
        stmt = stmt.where(DataSource.kb_id == kb_id)
    if source_type:
        stmt = stmt.where(DataSource.source_type == source_type)
    if enabled_only:
        stmt = stmt.where(DataSource.enabled == True)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Apply pagination
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def get_data_source(db: AsyncSession, source_id: int) -> Optional[DataSource]:
    """Get a data source by ID"""
    result = await db.execute(select(DataSource).where(DataSource.id == source_id))
    return result.scalar_one_or_none()


async def create_data_source(db: AsyncSession, data: DataSourceCreate) -> DataSource:
    """Create a new data source"""
    # Merge type-specific config into config_json
    config_json = data.config_json.copy() if data.config_json else {}

    if data.database_config:
        config_json["database_config"] = data.database_config.model_dump()
    if data.web_page_config:
        config_json["web_page_config"] = data.web_page_config.model_dump()
    if data.wechat_config:
        config_json["wechat_config"] = data.wechat_config.model_dump()
    if data.api_config:
        config_json["api_config"] = data.api_config.model_dump()
    if data.storage_config:
        config_json["storage_config"] = data.storage_config.model_dump()

    source = DataSource(
        name=data.name,
        source_type=data.source_type.value,
        description=data.description,
        kb_id=data.kb_id,
        sync_mode=data.sync_mode.value,
        cron_expression=data.cron_expression,
        auto_process=data.auto_process,
        enabled=data.enabled,
        tags=",".join(data.tags) if data.tags else None,
        config_json=config_json,
    )

    db.add(source)
    await db.commit()
    await db.refresh(source)

    logger.info("Data source created | id=%d name=%s type=%s", source.id, source.name, source.source_type)
    return source


async def update_data_source(
    db: AsyncSession,
    source_id: int,
    data: DataSourceUpdate,
) -> Optional[DataSource]:
    """Update a data source"""
    source = await get_data_source(db, source_id)
    if not source:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Merge config updates
    if "config_json" in update_data and update_data["config_json"]:
        if source.config_json:
            source.config_json.update(update_data["config_json"])
        else:
            source.config_json = update_data["config_json"]
        del update_data["config_json"]

    # Handle type-specific config merges
    for config_key in ["database_config", "web_page_config", "wechat_config", "api_config", "storage_config"]:
        if config_key in update_data and update_data[config_key]:
            if source.config_json:
                source.config_json[config_key] = update_data[config_key]
            else:
                source.config_json = {config_key: update_data[config_key]}
            del update_data[config_key]

    # Handle tags conversion
    if "tags" in update_data and isinstance(update_data["tags"], list):
        update_data["tags"] = ",".join(update_data["tags"])

    # Convert enums to string values
    if "sync_mode" in update_data and update_data["sync_mode"]:
        update_data["sync_mode"] = update_data["sync_mode"].value if hasattr(update_data["sync_mode"], 'value') else update_data["sync_mode"]

    for key, value in update_data.items():
        if value is not None:
            setattr(source, key, value)

    await db.flush()
    await db.refresh(source)

    logger.info("Data source updated | id=%d name=%s", source.id, source.name)
    return source


async def delete_data_source(db: AsyncSession, source_id: int) -> bool:
    """Delete a data source"""
    source = await get_data_source(db, source_id)
    if not source:
        return False

    await db.delete(source)
    await db.flush()

    logger.info("Data source deleted | id=%d name=%s", source_id, source.name)
    return True


# ============================================================
# Sync Job Management
# ============================================================

async def create_sync_job(
    db: AsyncSession,
    data_source_id: int,
    full_sync: bool = True,
    trigger_by: str = "manual",
) -> Optional[SyncJob]:
    """Create a new sync job"""
    source = await get_data_source(db, data_source_id)
    if not source or not source.enabled:
        return None

    # Update source status
    source.status = DataSourceStatus.SYNCING.value
    source.last_sync_status = None

    job = SyncJob(
        data_source_id=data_source_id,
        status=SyncJobStatus.PENDING.value,
        trigger_by=trigger_by,
        full_sync=full_sync,
    )

    db.add(job)
    await db.flush()
    await db.refresh(job)

    logger.info("Sync job created | job_id=%d source_id=%d type=%s", job.id, data_source_id, "full" if full_sync else "incremental")
    return job


async def start_sync_job(db: AsyncSession, job_id: int) -> Optional[SyncJob]:
    """Mark sync job as started"""
    job = await db.get(SyncJob, job_id)
    if not job:
        return None

    job.status = SyncJobStatus.RUNNING.value
    job.started_at = datetime.utcnow()

    # Update source status
    source = await get_data_source(db, job.data_source_id)
    if source:
        source.status = DataSourceStatus.SYNCING.value

    await db.flush()
    return job


async def complete_sync_job(
    db: AsyncSession,
    job_id: int,
    items_synced: int = 0,
    items_failed: int = 0,
    error_message: Optional[str] = None,
) -> Optional[SyncJob]:
    """Mark sync job as completed or failed"""
    job = await db.get(SyncJob, job_id)
    if not job:
        return None

    job.completed_at = datetime.utcnow()
    job.items_synced = items_synced
    job.items_failed = items_failed
    job.progress_percent = 100

    if error_message:
        job.status = SyncJobStatus.FAILED.value
        job.error_message = error_message
        status = DataSourceStatus.ERROR
    else:
        job.status = SyncJobStatus.COMPLETED.value
        status = DataSourceStatus.ACTIVE

    # Update source status
    source = await get_data_source(db, job.data_source_id)
    if source:
        source.status = status.value
        source.last_sync_at = datetime.utcnow()
        source.last_sync_status = job.status
        source.sync_message = error_message
        source.items_synced += items_synced
        source.items_failed += items_failed

    await db.flush()
    logger.info("Sync job completed | job_id=%d synced=%d failed=%d", job_id, items_synced, items_failed)
    return job


async def update_sync_progress(
    db: AsyncSession,
    job_id: int,
    progress_percent: int,
    items_synced: int = 0,
) -> Optional[SyncJob]:
    """Update sync job progress"""
    job = await db.get(SyncJob, job_id)
    if not job:
        return None

    job.progress_percent = min(progress_percent, 100)
    job.items_synced = items_synced

    await db.flush()
    return job


# ============================================================
# Synced Item Management
# ============================================================

async def create_synced_item(
    db: AsyncSession,
    sync_job_id: int,
    data_source_id: int,
    external_id: str,
    title: str,
    content: Optional[str] = None,
    url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> SyncedItem:
    """Create or update a synced item"""
    # Check for existing item
    existing = await db.execute(
        select(SyncedItem).where(
            SyncedItem.data_source_id == data_source_id,
            SyncedItem.external_id == external_id,
        )
    )
    item = existing.scalar_one_or_none()

    if item:
        # Update existing
        item.title = title
        item.content = content
        item.url = url
        item.metadata_json = metadata
        item.sync_job_id = sync_job_id
    else:
        # Create new
        item = SyncedItem(
            sync_job_id=sync_job_id,
            data_source_id=data_source_id,
            external_id=external_id,
            title=title,
            content=content,
            url=url,
            metadata_json=metadata,
        )
        db.add(item)

    await db.flush()
    return item


async def get_sync_job_status(db: AsyncSession, job_id: int) -> dict:
    """Get sync job status with details"""
    job = await db.get(SyncJob, job_id)
    if not job:
        return {"error": "Job not found"}

    return {
        "id": job.id,
        "data_source_id": job.data_source_id,
        "status": job.status,
        "trigger_by": job.trigger_by,
        "full_sync": job.full_sync,
        "items_synced": job.items_synced,
        "items_failed": job.items_failed,
        "progress_percent": job.progress_percent,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }


# ============================================================
# Data Source Presets
# ============================================================

from app.schemas.data_source import COMMON_DATA_SOURCE_PRESETS, DataSourcePreset


def get_data_source_presets(source_type: Optional[str] = None) -> list[DataSourcePreset]:
    """Get available data source presets"""
    if source_type:
        return [p for p in COMMON_DATA_SOURCE_PRESETS if p.source_type.value == source_type]
    return list(COMMON_DATA_SOURCE_PRESETS)
