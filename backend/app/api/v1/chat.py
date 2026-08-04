"""
[DEPRECATED] Chat completions API - 已废弃

此端点已废弃，请使用 /api/v1/agents/{agent_id}/execute/stream

原功能说明:
Chat completions API: RAG-grounded Q&A with streaming support.

Integrates:
- query expansion (HyDE, keyword expansion)
- vector retrieval
- reranking
- conversation memory (Redis)
- LLM generation with citations
- hallucination detection
"""
# ============================================================
# [已废弃] Chat Completions API
#
# 此端点已废弃，请使用：POST /api/v1/agents/{agent_id}/execute/stream
#
# 如需恢复此端点，取消下面路由器的注释即可
# ============================================================

# from __future__ import annotations
# import json
# import logging
# from typing import Optional
# from fastapi import APIRouter, Depends, HTTPException
# from fastapi.responses import StreamingResponse
# from sqlalchemy.ext.asyncio import AsyncSession
# import redis.asyncio as aioredis

# from app.core.database import get_db
# from app.core.redis_client import get_redis
# from app.core.milvus_client import get_milvus_client
# from app.models.knowledge_base import KnowledgeBase
# from app.schemas.chat import ChatRequest, ChatResponse
# from app.services.retrieval_service import search_chunks as retrieval_search
# from app.services.retrieval_service import _rerank_results
# from app.services.query_expansion import expand_query, hyde_expand
# from app.services.synonym_service import SynonymService
# from app.services.conversation_memory import ConversationMemory
# from app.services.llm_service import generate_rag_response
# from app.schemas.retrieval import SearchRequest
# from app.utils.exceptions import NotFoundException
# from app.core.auth import get_current_user
# from app.models.user import User

# logger = logging.getLogger("app.api.chat")

# router = APIRouter(prefix="/chat", tags=["Chat Completions"])


# @router.post("/completions")
# async def chat_completions_deprecated(
#     request: ChatRequest,
#     db: AsyncSession = Depends(get_db),
#     redis: aioredis.Redis = Depends(get_redis),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     [DEPRECATED] 已废弃的 RAG chat completion API
#
#     请使用：/api/v1/agents/{agent_id}/execute/stream
#     """
#     raise HTTPException(
#         status_code=410,
#         detail="此端点已废弃，请使用 /api/v1/agents/{agent_id}/execute/stream"
#     )
