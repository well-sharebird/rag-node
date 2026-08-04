"""
Conversation service - 对话历史服务
"""
from __future__ import annotations
import logging
import json
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.models.conversation import Conversation, ConversationMessage
from packages.agent.schemas.conversation import ConversationCreate, ConversationUpdate

logger = logging.getLogger("app.services.conversation")


async def create_conversation(
    db: AsyncSession,
    data: ConversationCreate,
    user_id: Optional[str] = None,
) -> Conversation:
    """创建新对话"""
    conversation = Conversation(
        user_id=user_id,
        title=data.title or "新对话",
        kb_ids=json.dumps(data.kb_ids) if data.kb_ids else None,
        is_active=True,
        is_archived=False,
        message_count=0,
    )

    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info("Conversation created | id=%s user=%s", conversation.id, user_id)
    return conversation


async def get_conversation(db: AsyncSession, conv_id: str) -> Optional[Conversation]:
    """获取对话详情"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    return result.scalar_one_or_none()


async def list_conversations(
    db: AsyncSession,
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
) -> List[Conversation]:
    """获取对话列表"""
    query = select(Conversation).where(Conversation.is_active == True)

    if user_id:
        query = query.where(Conversation.user_id == user_id)

    if not include_archived:
        query = query.where(Conversation.is_archived == False)

    query = query.order_by(Conversation.last_message_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_conversation_messages(
    db: AsyncSession,
    conv_id: str,
    limit: int = 100,
) -> List[ConversationMessage]:
    """获取对话消息列表"""
    query = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.message_index.asc())
        .limit(limit)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


async def add_message(
    db: AsyncSession,
    conv_id: str,
    role: str,
    content: str,
    sources: Optional[List[dict]] = None,
    token_count: Optional[int] = None,
    latency_ms: Optional[int] = None,
    model_used: Optional[str] = None,
) -> ConversationMessage:
    """添加消息到对话"""
    # 获取当前消息计数
    conv = await get_conversation(db, conv_id)
    if not conv:
        raise ValueError(f"Conversation {conv_id} not found")

    message_index = conv.message_count + 1

    message = ConversationMessage(
        conversation_id=conv_id,
        role=role,
        content=content,
        sources=json.dumps(sources) if sources else None,
        token_count=token_count,
        latency_ms=latency_ms,
        model_used=model_used,
        message_index=message_index,
    )

    db.add(message)

    # 更新对话计数
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conv_id)
        .values(
            message_count=message_index,
            last_message_at=datetime.utcnow(),
        )
    )

    await db.commit()
    await db.refresh(message)

    logger.info("Message added | conv=%s role=%s index=%d", conv_id, role, message_index)
    return message


async def update_conversation(
    db: AsyncSession,
    conv_id: str,
    data: ConversationUpdate,
) -> Optional[Conversation]:
    """更新对话"""
    values = {}
    if data.title is not None:
        values["title"] = data.title
    if data.is_archived is not None:
        values["is_archived"] = data.is_archived

    if not values:
        return await get_conversation(db, conv_id)

    await db.execute(
        update(Conversation).where(Conversation.id == conv_id).values(**values)
    )
    await db.commit()

    return await get_conversation(db, conv_id)


async def delete_conversation(db: AsyncSession, conv_id: str) -> bool:
    """删除对话（软删除，标记为非 active）"""
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conv_id)
        .values(is_active=False, is_archived=True)
    )
    await db.commit()

    logger.info("Conversation archived | id=%s", conv_id)
    return True


async def hard_delete_conversation(db: AsyncSession, conv_id: str) -> bool:
    """彻底删除对话及消息"""
    # 先删除消息
    await db.execute(
        delete(ConversationMessage).where(ConversationMessage.conversation_id == conv_id)
    )
    # 再删除对话
    await db.execute(delete(Conversation).where(Conversation.id == conv_id))
    await db.commit()

    logger.info("Conversation deleted | id=%s", conv_id)
    return True


async def search_conversations(
    db: AsyncSession,
    query: str,
    user_id: Optional[str] = None,
    limit: int = 20,
) -> List[Conversation]:
    """搜索对话（按标题）"""
    stmt = (
        select(Conversation)
        .where(Conversation.title.ilike(f"%{query}%"))
        .where(Conversation.is_active == True)
        .limit(limit)
    )

    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_or_update_conversation_from_agent(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    agent_id: Optional[str] = None,
    title: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    kb_ids: Optional[List[str]] = None,
) -> Conversation:
    """
    从 Agent 执行结果创建或更新会话

    用于 Agent 执行后自动保存会话历史

    Args:
        db: 数据库会话
        user_id: 用户 ID
        session_id: 会话 ID（用于标识同一轮对话）
        agent_id: Agent ID
        title: 会话标题（可选，默认用第一条消息生成）
        messages: 消息列表 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        kb_ids: 绑定的知识库 ID 列表

    Returns:
        Conversation: 创建或更新的会话记录
    """
    from sqlalchemy import select

    # 尝试查找已存在的会话（通过 session_id 关联）
    # 这里使用 metadata_json 存储 session_id
    existing = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .where(Conversation.is_active == True)
        .order_by(Conversation.created_at.desc())
        .limit(100)
    )
    conversations = existing.scalars().all()

    # 查找匹配的 session_id
    target_conv = None
    for conv in conversations:
        if conv.metadata_json:
            import json
            try:
                metadata = json.loads(conv.metadata_json)
                if metadata.get("session_id") == session_id:
                    target_conv = conv
                    break
            except:
                pass

    if target_conv:
        # 更新现有会话
        if messages:
            # 添加新消息
            for msg in messages:
                conversation_message = ConversationMessage(
                    conversation_id=target_conv.id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    message_index=target_conv.message_count + 1,
                )
                db.add(conversation_message)
                target_conv.message_count += 1
            target_conv.last_message_at = datetime.utcnow()

        # 更新标题（如果提供了新标题且当前标题为空或为默认值）
        if title and (not target_conv.title or target_conv.title == "新对话"):
            target_conv.title = title

        await db.commit()
        await db.refresh(target_conv)
        logger.info("Conversation updated | id=%s user=%s", target_conv.id, user_id)
        return target_conv
    else:
        # 创建新会话
        conv_title = title or "新对话"
        if messages and messages[0].get("role") == "user":
            # 用用户问题前 50 字作为标题
            first_msg = messages[0].get("content", "")[:50]
            if first_msg:
                conv_title = first_msg

        conversation = Conversation(
            user_id=user_id,
            title=conv_title,
            kb_ids=json.dumps(kb_ids) if kb_ids else None,
            is_active=True,
            is_archived=False,
            message_count=0,
            metadata_json=json.dumps({"session_id": session_id, "agent_id": agent_id}) if agent_id or session_id else None,
        )

        db.add(conversation)
        await db.flush()  # 获取生成的 ID

        # 添加消息
        if messages:
            for idx, msg in enumerate(messages):
                conversation_message = ConversationMessage(
                    conversation_id=conversation.id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    message_index=idx + 1,
                )
                db.add(conversation_message)
            conversation.message_count = len(messages)
            conversation.last_message_at = datetime.utcnow()

        await db.commit()
        await db.refresh(conversation)

        logger.info("Conversation created | id=%s user=%s", conversation.id, user_id)
        return conversation
