"""
Agent 运行时 API - 简化版

已删除：
- POST /run - Agent 运行（非流式）
- POST /run/stream - Agent 运行（流式）

原因：功能与 /{agent_id}/execute/stream 重叠，前端未使用

保留：
- POST /{agent_id}/memory/clear - 清除 Agent 记忆
- GET /{agent_id}/memory - 获取 Agent 对话历史
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.agent import AgentConfig

router = APIRouter(prefix="/agents", tags=["agents-runtime"])


@router.post("/{agent_id}/memory/clear")
async def clear_agent_memory(
    agent_id: str,
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除 Agent 的会话记忆"""
    from app.services.agent_memory_service import AgentMemoryService

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 使用 AgentMemoryService 清除记忆
    memory_service = AgentMemoryService(db)
    thread_id = f"{current_user.id}:{agent_id}:{session_id}"
    await memory_service.clear_conversation(agent_id, current_user.id, thread_id)

    return {"message": "Memory cleared"}


@router.get("/{agent_id}/memory")
async def get_agent_memory(
    agent_id: str,
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 Agent 的对话历史"""
    from app.services.agent_memory_service import AgentMemoryService

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    memory_service = AgentMemoryService(db)
    thread_id = f"{current_user.id}:{agent_id}:{session_id}"
    messages = await memory_service.get_conversation(agent_id, current_user.id, thread_id)

    return {"messages": messages}
