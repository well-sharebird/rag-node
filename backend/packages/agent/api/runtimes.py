"""
Agent Runtime API

提供 Runtime 生命周期管理接口
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User

from packages.agent.models.runtime import AgentRuntime, AgentRuntimeEvent
from packages.agent.models.agent import AgentConfig
from packages.agent.models.workspace import Workspace
from packages.agent.services.runtime_service import RuntimeService
from packages.agent.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtimes", tags=["runtimes"])


@router.post("/")
async def create_runtime(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建 Agent Runtime

    1. 验证 Agent 存在且有权限
    2. 获取或创建工作区
    3. 创建 Runtime 实例
    """
    # 验证 Agent
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.id == agent_id,
            AgentConfig.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 获取工作区
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_or_create_workspace(current_user)

    # 创建 Runtime
    runtime_service = RuntimeService(db)
    runtime = await runtime_service.create_runtime(
        agent=agent,
        workspace=workspace,
        created_by=current_user.id,
    )

    logger.info(f"Runtime created: {runtime.id} for agent {agent_id}")

    return {
        "id": runtime.id,
        "agent_id": runtime.agent_id,
        "workspace_id": runtime.workspace_id,
        "status": runtime.status,
        "sandbox_type": runtime.sandbox_type,
        "manifest": runtime.manifest,
        "created_at": runtime.created_at.isoformat(),
    }


@router.get("/{runtime_id}")
async def get_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 Runtime 详情"""
    runtime_service = RuntimeService(db)
    runtime = await runtime_service.get_runtime(runtime_id)

    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    # 权限检查
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)

    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    return {
        "id": runtime.id,
        "agent_id": runtime.agent_id,
        "workspace_id": runtime.workspace_id,
        "status": runtime.status,
        "sandbox_type": runtime.sandbox_type,
        "sandbox_id": runtime.sandbox_id,
        "sandbox_config": runtime.sandbox_config,
        "manifest": runtime.manifest,
        "resource_usage": runtime.resource_usage,
        "last_active_at": runtime.last_active_at.isoformat() if runtime.last_active_at else None,
        "idle_seconds": runtime.idle_seconds,
        "start_count": runtime.start_count,
        "created_at": runtime.created_at.isoformat(),
        "started_at": runtime.started_at.isoformat() if runtime.started_at else None,
    }


@router.post("/{runtime_id}/start")
async def start_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """启动 Runtime"""
    runtime_service = RuntimeService(db)

    # 权限检查
    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 启动
    runtime = await runtime_service.start_runtime(runtime_id)

    logger.info(f"Runtime started: {runtime_id}")

    return {
        "id": runtime.id,
        "status": runtime.status,
        "sandbox_id": runtime.sandbox_id,
        "started_at": runtime.started_at.isoformat(),
    }


@router.post("/{runtime_id}/stop")
async def stop_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """停止 Runtime"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    runtime = await runtime_service.stop_runtime(runtime_id)

    logger.info(f"Runtime stopped: {runtime_id}")

    return {
        "id": runtime.id,
        "status": runtime.status,
        "stopped_at": runtime.stopped_at.isoformat(),
    }


@router.post("/{runtime_id}/sleep")
async def sleep_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """休眠 Runtime (节省资源)"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    runtime = await runtime_service.sleep_runtime(runtime_id)

    logger.info(f"Runtime slept: {runtime_id}")

    return {
        "id": runtime.id,
        "status": runtime.status,
    }


@router.post("/{runtime_id}/wake")
async def wake_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """唤醒 Runtime (从休眠恢复)"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    runtime = await runtime_service.wake_runtime(runtime_id)

    logger.info(f"Runtime woken: {runtime_id}")

    return {
        "id": runtime.id,
        "status": runtime.status,
    }


@router.get("/{runtime_id}/sessions")
async def list_runtime_sessions(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出 Runtime 下的所有 Session"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    sessions = await runtime_service.get_runtime_sessions(runtime_id)

    return {
        "sessions": [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "context_used_tokens": s.context_used_tokens,
                "last_activity_at": s.last_activity_at.isoformat() if s.last_activity_at else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/{runtime_id}/events")
async def list_runtime_events(
    runtime_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出 Runtime 事件日志"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询事件
    result = await db.execute(
        select(AgentRuntimeEvent)
        .where(AgentRuntimeEvent.runtime_id == runtime_id)
        .order_by(AgentRuntimeEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_data": e.event_data,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    }


@router.delete("/{runtime_id}")
async def delete_runtime(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 Runtime"""
    runtime_service = RuntimeService(db)

    runtime = await runtime_service.get_runtime(runtime_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)
    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    await runtime_service.delete_runtime(runtime_id)

    logger.info(f"Runtime deleted: {runtime_id}")

    return {"message": "Runtime deleted"}
