from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.core.deps import DBSession
from app.schemas.model import (
    ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse,
    ModelConfigList, ModelTestRequest, ModelTestResult,
    ModelPreset, ModelType
)
from app.services import model_service

logger = logging.getLogger("app.api.models")

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelConfigList)
async def list_models(
    db: DBSession,
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    adapter_type: Optional[str] = Query(None, description="Filter by adapter type"),
    enabled_only: bool = Query(False, description="Only return enabled models"),
):
    """List all model configurations"""
    models = await model_service.list_models(
        db,
        model_type=model_type,
        adapter_type=adapter_type,
        enabled_only=enabled_only,
    )
    return ModelConfigList(
        items=[ModelConfigResponse.model_validate(m) for m in models],
        total=len(models),
    )


@router.get("/presets", response_model=list[ModelPreset])
async def list_model_presets(
    model_type: Optional[str] = Query(None, description="Filter presets by type"),
):
    """Get available model presets for quick setup"""
    return model_service.get_available_presets(model_type)


@router.get("/{model_id}", response_model=ModelConfigResponse)
async def get_model(db: DBSession, model_id: int):
    """Get a specific model configuration"""
    model = await model_service.get_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelConfigResponse.model_validate(model)


@router.post("", response_model=ModelConfigResponse, status_code=201)
async def create_model(db: DBSession, data: ModelConfigCreate):
    """Create a new model configuration"""
    model = await model_service.create_model(db, data)
    return ModelConfigResponse.model_validate(model)


@router.put("/{model_id}", response_model=ModelConfigResponse)
async def update_model(db: DBSession, model_id: int, data: ModelConfigUpdate):
    """Update a model configuration"""
    model = await model_service.update_model(db, model_id, data)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelConfigResponse.model_validate(model)


@router.delete("/{model_id}", status_code=204)
async def delete_model(db: DBSession, model_id: int):
    """Delete a model configuration"""
    success = await model_service.delete_model(db, model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")


@router.post("/{model_id}/test", response_model=ModelTestResult)
async def test_model(db: DBSession, model_id: int, request: ModelTestRequest = None):
    """Test model connection and functionality"""
    test_input = request.test_input if request else None
    result = await model_service.test_model_connection(db, model_id, test_input)
    return ModelTestResult(**result)


@router.get("/default/{model_type}", response_model=ModelConfigResponse | None)
async def get_default_model(db: DBSession, model_type: str):
    """Get the default model for a specific type"""
    model = await model_service.get_default_model(db, model_type)
    if not model:
        return None
    return ModelConfigResponse.model_validate(model)
