from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.core.deps import DBSession
from app.schemas.data_source import (
    DataSourceCreate, DataSourceUpdate, DataSourceResponse,
    DataSourceList, DataSourcePreset,
    SyncJobCreate, SyncJobResponse,
)
from app.services import data_source_service

logger = logging.getLogger("app.api.data_sources")

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("", response_model=DataSourceList)
async def list_data_sources(
    db: DBSession,
    kb_id: Optional[int] = Query(None, description="Filter by knowledge base ID"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    enabled_only: bool = Query(False, description="Only return enabled sources"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all data sources with pagination"""
    items, total = await data_source_service.list_data_sources(
        db, kb_id, source_type, enabled_only, page, page_size
    )
    return DataSourceList(
        items=[DataSourceResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/presets", response_model=list[DataSourcePreset])
async def list_data_source_presets(
    source_type: Optional[str] = Query(None, description="Filter presets by type"),
):
    """Get available data source presets for quick setup"""
    return data_source_service.get_data_source_presets(source_type)


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(db: DBSession, source_id: int):
    """Get a specific data source"""
    source = await data_source_service.get_data_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return DataSourceResponse.model_validate(source)


@router.post("", response_model=DataSourceResponse, status_code=201)
async def create_data_source(db: DBSession, data: DataSourceCreate):
    """Create a new data source"""
    source = await data_source_service.create_data_source(db, data)
    return DataSourceResponse.model_validate(source)


@router.put("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(db: DBSession, source_id: int, data: DataSourceUpdate):
    """Update a data source"""
    source = await data_source_service.update_data_source(db, source_id, data)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return DataSourceResponse.model_validate(source)


@router.delete("/{source_id}", status_code=204)
async def delete_data_source(db: DBSession, source_id: int):
    """Delete a data source"""
    success = await data_source_service.delete_data_source(db, source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Data source not found")


@router.post("/{source_id}/sync", response_model=SyncJobResponse)
async def trigger_sync(
    db: DBSession,
    source_id: int,
    full_sync: bool = Query(True, description="Full sync vs incremental"),
):
    """Trigger a sync job for a data source"""
    job = await data_source_service.create_sync_job(
        db, source_id, full_sync=full_sync, trigger_by="api"
    )
    if not job:
        raise HTTPException(status_code=400, detail="Cannot create sync job. Source may be disabled.")

    # Start the sync immediately (in real app, this would be async)
    await data_source_service.start_sync_job(db, job.id)

    return SyncJobResponse.model_validate(job)


@router.get("/sync/{job_id}", response_model=SyncJobResponse)
async def get_sync_job_status(db: DBSession, job_id: int):
    """Get sync job status"""
    job = await db.get(data_source_service.SyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    return SyncJobResponse.model_validate(job)


@router.get("/{source_id}/sync-history", response_model=list[SyncJobResponse])
async def get_sync_history(db: DBSession, source_id: int, limit: int = Query(20, ge=1, le=100)):
    """Get sync history for a data source"""
    from app.models.data_source import SyncJob
    result = await db.execute(
        select(SyncJob)
        .where(SyncJob.data_source_id == source_id)
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
    )
    jobs = list(result.scalars().all())
    return [SyncJobResponse.model_validate(j) for j in jobs]


# Import select for the sync history endpoint
from sqlalchemy import select
