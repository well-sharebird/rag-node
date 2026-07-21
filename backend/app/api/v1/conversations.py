"""
Conversations API - 对话历史管理
"""
import logging
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List

from app.core.deps import DBSession
from app.core.redis_client import get_redis
import redis.asyncio as aioredis

from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    ConversationListResponse,
    ConversationWithMessagesResponse,
    MessageResponse,
)
from app.services import conversation_service

logger = logging.getLogger("app.api.conversations")
router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    db: DBSession,
    data: ConversationCreate,
    user_id: Optional[str] = Query(None, description="User ID"),
):
    """创建新对话"""
    conv = await conversation_service.create_conversation(db, data, user_id)
    return ConversationResponse(
        id=conv.id,
        user_id=conv.user_id,
        title=conv.title,
        kb_ids=conv.kb_ids.split(",") if conv.kb_ids else None,
        is_active=conv.is_active,
        is_archived=conv.is_archived,
        message_count=conv.message_count,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    db: DBSession,
    user_id: Optional[str] = Query(None, description="User ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
):
    """获取对话列表"""
    items = await conversation_service.list_conversations(
        db, user_id, limit, offset, include_archived
    )

    return ConversationListResponse(
        items=[
            ConversationResponse(
                id=c.id,
                user_id=c.user_id,
                title=c.title,
                kb_ids=c.kb_ids.split(",") if c.kb_ids else None,
                is_active=c.is_active,
                is_archived=c.is_archived,
                message_count=c.message_count,
                last_message_at=c.last_message_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in items
        ],
        total=len(items),
    )


@router.get("/{conv_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation_with_messages(
    db: DBSession,
    conv_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """获取对话详情及消息列表"""
    conv = await conversation_service.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await conversation_service.get_conversation_messages(db, conv_id, limit)

    return ConversationWithMessagesResponse(
        id=conv.id,
        title=conv.title,
        kb_ids=conv.kb_ids.split(",") if conv.kb_ids else None,
        message_count=conv.message_count,
        last_message_at=conv.last_message_at,
        messages=[
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                sources=json.loads(m.sources) if m.sources else None,
                token_count=m.token_count,
                latency_ms=m.latency_ms,
                model_used=m.model_used,
                message_index=m.message_index,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.put("/{conv_id}", response_model=ConversationResponse)
async def update_conversation(
    db: DBSession,
    conv_id: str,
    data: ConversationUpdate,
):
    """更新对话（标题/归档）"""
    conv = await conversation_service.update_conversation(db, conv_id, data)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=conv.id,
        user_id=conv.user_id,
        title=conv.title,
        kb_ids=conv.kb_ids.split(",") if conv.kb_ids else None,
        is_active=conv.is_active,
        is_archived=conv.is_archived,
        message_count=conv.message_count,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conv_id}")
async def delete_conversation(db: DBSession, conv_id: str, hard: bool = Query(False)):
    """删除对话（软删除或彻底删除）"""
    if hard:
        success = await conversation_service.hard_delete_conversation(db, conv_id)
    else:
        success = await conversation_service.delete_conversation(db, conv_id)

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"status": "deleted", "conversation_id": conv_id}


@router.get("/search/{query}")
async def search_conversations(
    db: DBSession,
    query: str,
    user_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """搜索对话"""
    items = await conversation_service.search_conversations(db, query, user_id, limit)

    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "message_count": c.message_count,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            }
            for c in items
        ],
        "total": len(items),
    }
