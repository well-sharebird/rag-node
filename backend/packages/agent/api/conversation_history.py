"""
会话历史 API

提供会话历史的查询、归档和恢复功能
"""
import logging
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.services.conversation_archive_service import ConversationArchiveService

logger = logging.getLogger("app.api.conversation_history")

router = APIRouter(prefix="/conversation-history", tags=["conversation-history"])


class ConversationHistoryItem(BaseModel):
    """会话历史项"""
    thread_id: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    message_count: int
    last_message_at: str
    source: str  # "hot" | "archive"
    archive_tier: Optional[str] = None  # "warm" | "cold"
    summary: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """会话历史列表响应"""
    items: List[ConversationHistoryItem]
    total: int


@router.get("", response_model=ConversationHistoryResponse)
async def list_conversation_history(
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    agent_id: Optional[str] = Query(None, description="智能体 ID 过滤"),
    time_range: Optional[str] = Query(None, description="时间范围：7d|30d|month|all"),
    month: Optional[str] = Query(None, description="月份：2026-01（当 time_range=month 时使用"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取会话历史列表

    返回跨热/温/冷三层的会话历史列表，按最后消息时间排序

    时间范围说明：
    - 7d: 最近 7 天
    - 30d: 最近 30 天
    - month: 指定月份（需配合 month 参数）
    - all: 全部（默认）
    """
    service = ConversationArchiveService(db)

    try:
        items, total = await service.get_conversation_history(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            agent_id=agent_id,
            time_range=time_range,
            month=month,
        )

        return {
            "items": items,
            "total": total,
        }

    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=dict)
async def get_conversation_history_stats(
    agent_id: Optional[str] = Query(None, description="智能体 ID 过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取会话历史统计（按时间段分组）

    返回：
    - last_7d: 最近 7 天的会话数
    - last_30d: 最近 30 天的会话数
    - months: 各月份的会话数 {"2026-01": 10, "2025-12": 15, ...}
    """
    service = ConversationArchiveService(db)

    try:
        stats = await service.get_conversation_history_stats(
            user_id=current_user.id,
            agent_id=agent_id,
        )

        return stats

    except Exception as e:
        logger.error(f"Failed to get conversation history stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取指定会话的完整消息历史

    自动从热存储或归档中恢复数据
    """
    from sqlalchemy import select
    from packages.agent.models.agent import AgentMemory
    from packages.agent.models.conversation_archive import ConversationArchive

    try:
        # 1. 先尝试从热存储获取
        result = await db.execute(
            select(AgentMemory)
            .where(AgentMemory.thread_id == thread_id)
            .where(AgentMemory.user_id == current_user.id)
            .where(AgentMemory.memory_type == "conversation")
            .order_by(AgentMemory.created_at)
        )
        memories = result.scalars().all()

        if memories:
            # 合并所有消息，转换为前端期望的格式
            all_messages = []
            for mem in memories:
                content = mem.content.get("messages", [])
                if isinstance(content, list):
                    for msg in content:
                        if isinstance(msg, str):
                            # 字符串消息，根据内容判断是用户还是 AI
                            # 用户消息通常较短，AI 消息通常较长且有格式化
                            is_ai = len(msg) > 100 or msg.startswith('\n') or '**' in msg
                            all_messages.append({
                                "role": "assistant" if is_ai else "user",
                                "content": msg,
                                "timestamp": mem.created_at.isoformat() if mem.created_at else None,
                            })
                        elif isinstance(msg, dict):
                            # 对象消息，直接使用
                            all_messages.append(msg)
                elif isinstance(content, str):
                    is_ai = len(content) > 100 or content.startswith('\n') or '**' in content
                    all_messages.append({
                        "role": "assistant" if is_ai else "user",
                        "content": content,
                        "timestamp": mem.created_at.isoformat() if mem.created_at else None,
                    })
            return {"messages": all_messages, "source": "hot"}

        # 2. 从归档中获取
        result = await db.execute(
            select(ConversationArchive)
            .where(ConversationArchive.thread_id == thread_id)
            .where(ConversationArchive.user_id == current_user.id)
            .order_by(ConversationArchive.last_message_at.desc())
            .limit(1)
        )
        archive = result.scalar_one_or_none()

        if archive:
            service = ConversationArchiveService(db)
            raw_messages = await service.get_archive_content(archive.id)
            # 转换为前端期望的格式
            messages = []
            for idx, msg in enumerate(raw_messages):
                if isinstance(msg, str):
                    messages.append({
                        "role": "user" if idx % 2 == 0 else "assistant",
                        "content": msg,
                        "timestamp": archive.last_message_at.isoformat() if archive.last_message_at else None,
                    })
                elif isinstance(msg, dict):
                    messages.append(msg)
            return {
                "messages": messages,
                "source": "archive",
                "archive_tier": archive.archive_tier,
                "archive_id": archive.id,
            }

        raise HTTPException(status_code=404, detail="Conversation not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thread messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive/{archive_id}/restore")
async def restore_archive(
    archive_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    恢复归档的会话到热存储

    恢复后可以正常读写该会话
    """
    service = ConversationArchiveService(db)

    try:
        # 验证归档属于当前用户
        from sqlalchemy import select
        from packages.agent.models.conversation_archive import ConversationArchive

        result = await db.execute(
            select(ConversationArchive)
            .where(ConversationArchive.id == archive_id)
            .where(ConversationArchive.user_id == current_user.id)
        )
        archive = result.scalar_one_or_none()

        if not archive:
            raise HTTPException(status_code=404, detail="Archive not found")

        await service.restore_archive(archive_id)

        return {
            "message": "Archive restored successfully",
            "thread_id": archive.thread_id,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive/run")
async def run_archive_job(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    手动触发归档任务

    仅管理员可用
    """
    # TODO: 添加权限检查
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin only")

    service = ConversationArchiveService(db)

    try:
        result = await service.archive_old_conversations()
        return {
            "message": "Archive job completed",
            "result": result,
        }

    except Exception as e:
        logger.error(f"Failed to run archive job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/{archive_id}")
async def get_archive_detail(
    archive_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取归档详情
    """
    from sqlalchemy import select
    from packages.agent.models.conversation_archive import ConversationArchive

    result = await db.execute(
        select(ConversationArchive)
        .where(ConversationArchive.id == archive_id)
        .where(ConversationArchive.user_id == current_user.id)
    )
    archive = result.scalar_one_or_none()

    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")

    return {
        "id": archive.id,
        "thread_id": archive.thread_id,
        "agent_id": archive.agent_id,
        "agent_name": archive.agent_name,
        "archive_tier": archive.archive_tier,
        "message_count": archive.message_count,
        "archive_size_bytes": archive.archive_size_bytes,
        "date_range_start": archive.date_range_start.isoformat(),
        "date_range_end": archive.date_range_end.isoformat(),
        "summary": archive.summary,
        "last_message_at": archive.last_message_at.isoformat(),
        "archived_at": archive.archived_at.isoformat(),
        "is_restored": archive.is_restored,
    }


@router.delete("/archive/{archive_id}")
async def delete_archive(
    archive_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除归档

  注意：此操作不可逆，会同时删除 MinIO 中的文件
    """
    from sqlalchemy import select, delete
    from packages.agent.models.conversation_archive import ConversationArchive

    result = await db.execute(
        select(ConversationArchive)
        .where(ConversationArchive.id == archive_id)
        .where(ConversationArchive.user_id == current_user.id)
    )
    archive = result.scalar_one_or_none()

    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")

    try:
        # 如果是冷归档，先删除 MinIO 文件
        if archive.archive_tier == "cold" and archive.archive_path:
            from packages.core.infra.minio_client import get_minio_client
            minio = get_minio_client()
            minio.remove_object(
                bucket="conversation-archives",
                object_name=archive.archive_path,
            )

        # 删除数据库记录
        await db.execute(
            delete(ConversationArchive)
            .where(ConversationArchive.id == archive_id)
        )
        await db.commit()

        return {"message": "Archive deleted successfully"}

    except Exception as e:
        logger.error(f"Failed to delete archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))
