"""人工审批 API - 敏感工具 HITL 闭环

- GET  /approvals/pending           当前用户待审批列表
- POST /approvals/{id}/approve      批准
- POST /approvals/{id}/reject       拒绝
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.core.harness.security.permission import PermissionEngine
from packages.agent.orchestrator.graph import Orchestrator

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ResumeRequest(BaseModel):
    """HITL 续跑参数：定位待续跑的子 Agent 与断点线程。"""
    sub_agent_id: str
    thread_id: str
    main_prompt: str | None = None


@router.get("/pending")
async def list_pending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的待审批列表（DB 持久化）"""
    engine = PermissionEngine(db, user_id=current_user.id)
    return await engine.get_pending_requests(user_id=current_user.id)


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批准一个权限请求"""
    engine = PermissionEngine(db, user_id=current_user.id)
    ok = await engine.approve_permission(request_id, approver_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="审批请求不存在或已处理")
    return {"success": True, "request_id": request_id}


@router.post("/{request_id}/reject")
async def reject_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拒绝一个权限请求"""
    engine = PermissionEngine(db, user_id=current_user.id)
    ok = await engine.reject_permission(request_id, approver_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="审批请求不存在或已处理")
    return {"success": True, "request_id": request_id}


@router.post("/{request_id}/resume")
async def resume_after_approval(
    request_id: str,
    body: ResumeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批准后从断点续跑子 Agent（完整 HITL 断点续跑，#3/#4）。

    前置：该审批请求必须已批准；否则拒绝续跑。
    内部经 OrchestratorRuntime.resume_sub_agent 重建同配置带 checkpointer 的子图，
    按 thread_id 从 DB 断点恢复执行（permission 层已短路放行已批工具）。
    """
    engine = PermissionEngine(db, user_id=current_user.id)
    if not await engine.is_approved(request_id):
        raise HTTPException(status_code=400, detail="审批请求未批准，无法续跑")
    rt = Orchestrator(db, user_id=current_user.id)
    try:
        result = await rt.resume_sub_agent(
            body.sub_agent_id, body.thread_id, main_prompt=body.main_prompt,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"续跑失败: {e}")
    return {**result, "request_id": request_id}
