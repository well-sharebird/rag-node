from __future__ import annotations
from fastapi import APIRouter

from packages.core.system.api.dashboard import router as dashboard_router
from packages.rag.api.knowledge_bases import router as kb_router
from packages.rag.api.documents import router as docs_router
from packages.rag.api.retrieval import router as retrieval_router
from packages.core.system.api.settings import router as settings_router
from packages.core.system.api.health import router as health_router
from packages.model_gateway.api.models import router as models_router
from packages.rag.api.data_sources import router as data_sources_router
from packages.core.system.api.metrics import router as metrics_router
from packages.core.system.api.users import router as users_router
from packages.core.system.api.prometheus import router as prometheus_router
from packages.model_gateway.api.token_usage import router as token_usage_router
from packages.agent.api.skills import router as skills_router
from packages.prompt.api.prompts import router as prompts_router
from packages.agent.api.conversation_history import router as conversation_history_router
from packages.core.system.api.auth import router as auth_router
from packages.core.system.api.admin import router as admin_router
from packages.agent.api.agents import router as agents_router
from packages.agent.api.agent_runtime import router as agent_runtime_router
from packages.agent.api.conversations import router as conversations_router
from packages.agent.api.feedback import router as feedback_router
from packages.agent.api.tracing import router as tracing_router
from packages.rag.api.evaluation import router as evaluation_router
from packages.rag.api.synonyms import router as synonyms_router
from packages.rag.api.desensitization import router as desensitization_router
from packages.model_gateway.api.model_gateway import router as model_gateway_router

# Agent Runtime & Workspace (新增)
from packages.agent.api.workspaces import router as workspaces_router
from packages.agent.api.runtimes import router as runtimes_router
from packages.agent.api.sessions import router as sessions_router
from packages.agent.api.code_execution import router as code_execution_router
from packages.agent.api.execution_traces import router as execution_traces_router
from packages.agent.api.approvals import router as approvals_router

# ============================================================
# 注意：chat.py 已废弃，不再使用
# 所有问答请求统一使用 /api/v1/agents/{agent_id}/execute/stream
# ============================================================

router = APIRouter()
router.include_router(workspaces_router)
router.include_router(runtimes_router)
router.include_router(sessions_router)
router.include_router(code_execution_router)
router.include_router(approvals_router)
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
router.include_router(agent_runtime_router)
router.include_router(conversations_router)
router.include_router(feedback_router)
router.include_router(tracing_router)
router.include_router(execution_traces_router)
router.include_router(evaluation_router)
router.include_router(synonyms_router)
router.include_router(desensitization_router)
router.include_router(model_gateway_router)
