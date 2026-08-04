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
from app.api.v1.metrics import router as metrics_router
from app.api.v1.users import router as users_router
from app.api.v1.prometheus import router as prometheus_router
from app.api.v1.token_usage import router as token_usage_router
from app.api.v1.skills import router as skills_router
from app.api.v1.prompts import router as prompts_router
from app.api.v1.conversation_history import router as conversation_history_router
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.agents import router as agents_router

# ============================================================
# 注意：chat.py 已废弃，不再使用
# 所有问答请求统一使用 /api/v1/agents/{agent_id}/execute/stream
# ============================================================

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(kb_router)
router.include_router(docs_router)
router.include_router(retrieval_router)
router.include_router(settings_router)
router.include_router(health_router)
router.include_router(models_router)
router.include_router(data_sources_router)
router.include_router(metrics_router)
router.include_router(users_router)
router.include_router(prometheus_router)
router.include_router(token_usage_router)
router.include_router(skills_router)
router.include_router(prompts_router)
router.include_router(conversation_history_router)
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(agents_router)
