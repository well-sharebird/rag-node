"""人工审批 API - 敏感工具 HITL 闭环

- GET  /approvals/pending           当前用户待审批列表
- POST /approvals/{id}/approve      批准
- POST /approvals/{id}/reject       拒绝
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.runtime_engine.permission import PermissionEngine

router = APIRouter(prefix="/approvals", tags=["approvals"])


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
