from __future__ import annotations
from fastapi import APIRouter

from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.knowledge_bases import router as kb_router
from app.api.v1.documents import router as docs_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.settings import router as settings_router
from app.api.v1.health import router as health_router
from app.api.v1.models import router as models_router
from app.api.v1.data_sources import router as data_sources_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(kb_router)
router.include_router(docs_router)
router.include_router(retrieval_router)
router.include_router(settings_router)
router.include_router(health_router)
router.include_router(models_router)
router.include_router(data_sources_router)
