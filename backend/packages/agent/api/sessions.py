"""
Agent Session API

提供 Session 创建和管理接口
"""
import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User

from packages.agent.models.session import AgentSession, AgentSessionMessage
from packages.agent.models.runtime import AgentRuntime
from packages.agent.services.runtime_service import RuntimeService
from packages.agent.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/")
async def create_session(
    runtime_id: str,
    name: Optional[str] = Query(None, description="会话名称"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新的 Session

    1. 验证 Runtime 存在且有权限访问
    2. 生成安全的会话令牌
    3. 创建 Session 记录
    """
    # 验证 Runtime
    result = await db.execute(
        select(AgentRuntime).where(AgentRuntime.id == runtime_id)
    )
    runtime = result.scalar_one_or_none()

    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    # 权限检查 - 验证工作区归属
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)

    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 生成安全的会话令牌
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # 创建 Session
    session = AgentSession(
        runtime_id=runtime_id,
        user_id=current_user.id,
        session_token_hash=token_hash,
        session_token_expires_at=datetime.utcnow() + timedelta(hours=24),
        name=name,
        status="active",
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"Session created: {session.id} for runtime {runtime_id}")

    return {
        "id": session.id,
        "runtime_id": session.runtime_id,
        "name": session.name,
        "status": session.status,
        "session_token": token,  # 只在创建时返回一次
        "expires_at": session.session_token_expires_at.isoformat(),
        "created_at": session.created_at.isoformat(),
    }


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 Session 详情"""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    return {
        "id": session.id,
        "runtime_id": session.runtime_id,
        "name": session.name,
        "status": session.status,
        "context_window_tokens": session.context_window_tokens,
        "context_used_tokens": session.context_used_tokens,
        "last_activity_at": session.last_activity_at.isoformat() if session.last_activity_at else None,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/{session_id}/messages")
async def list_session_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 Session 的消息历史"""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询消息
    msg_result = await db.execute(
        select(AgentSessionMessage)
        .where(AgentSessionMessage.session_id == session_id)
        .order_by(AgentSessionMessage.created_at)
        .limit(limit)
    )
    messages = msg_result.scalars().all()

    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "content_type": m.content_type,
                "tool_calls": m.tool_calls,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }


@router.post("/{session_id}/messages")
async def create_session_message(
    session_id: str,
    role: str,
    content: str,
    content_type: str = "text",
    tool_calls: Optional[dict] = None,
    referenced_file_ids: Optional[list[str]] = None,
    token_count: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建 Session 消息

    用于记录用户输入或 Agent 回复
    """
    # 验证 Session
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 创建消息
    message = AgentSessionMessage(
        session_id=session_id,
        role=role,
        content=content,
        content_type=content_type,
        tool_calls=tool_calls,
        referenced_file_ids=referenced_file_ids,
        token_count=token_count,
    )

    db.add(message)

    # 更新 Session 的活动时间和 token 使用
    session.update_activity()
    session.context_used_tokens += token_count

    await db.commit()
    await db.refresh(message)

    logger.info(f"Message created in session {session_id}, role: {role}")

    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


@router.post("/{session_id}/archive")
async def archive_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档 Session"""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    session.status = "archived"
    session.archived_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Session archived: {session_id}")

    return {"message": "Session archived"}


@router.post("/{session_id}/clear")
async def clear_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空 Session 的消息历史"""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 删除消息
    await db.execute(
        AgentSessionMessage.__table__.delete().where(
            AgentSessionMessage.session_id == session_id
        )
    )

    # 重置 token 计数
    session.context_used_tokens = 0
    session.update_activity()

    await db.commit()

    logger.info(f"Session messages cleared: {session_id}")

    return {"message": "Session messages cleared"}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 Session"""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限检查
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    await db.delete(session)
    await db.commit()

    logger.info(f"Session deleted: {session_id}")

    return {"message": "Session deleted"}
