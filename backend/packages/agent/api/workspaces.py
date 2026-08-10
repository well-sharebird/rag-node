"""
Workspace 工作区 API

提供工作区管理、文件操作等接口
"""
import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User

from packages.agent.models.workspace import Workspace, WorkspaceFile, WorkspaceAuditLog
from packages.agent.services.workspace_service import WorkspaceService, SecurityError, QuotaExceededError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/me")
async def get_my_workspace(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的工作区

    如果不存在会自动创建
    """
    service = WorkspaceService(db)
    workspace = await service.get_or_create_workspace(current_user)

    return {
        "id": workspace.id,
        "user_id": workspace.user_id,
        "root_path": workspace.root_path,
        "storage_quota_bytes": workspace.storage_quota_bytes,
        "storage_used_bytes": workspace.storage_used_bytes,
        "storage_used_percent": workspace.storage_used_percent,
        "status": workspace.status,
        "is_isolated": workspace.is_isolated,
        "created_at": workspace.created_at.isoformat(),
    }


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取工作区详情"""
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 权限检查
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    return {
        "id": workspace.id,
        "user_id": workspace.user_id,
        "root_path": workspace.root_path,
        "storage_quota_bytes": workspace.storage_quota_bytes,
        "storage_used_bytes": workspace.storage_used_bytes,
        "storage_used_percent": workspace.storage_used_percent,
        "status": workspace.status,
        "created_at": workspace.created_at.isoformat(),
    }


@router.get("/{workspace_id}/files")
async def list_workspace_files(
    workspace_id: str,
    session_id: Optional[str] = Query(None, description="过滤特定 Session 的文件"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出工作区中的文件"""
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询文件
    query = select(WorkspaceFile).where(
        WorkspaceFile.workspace_id == workspace_id
    )

    if session_id:
        query = query.where(WorkspaceFile.session_id == session_id)

    result = await db.execute(query.order_by(WorkspaceFile.created_at.desc()))
    files = result.scalars().all()

    return {
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "relative_path": f.relative_path,
                "file_size": f.file_size,
                "mime_type": f.mime_type,
                "source_type": f.source_type,
                "is_sandbox_generated": f.is_sandbox_generated,
                "scan_status": f.scan_status,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ]
    }


@router.post("/{workspace_id}/files")
async def upload_file(
    workspace_id: str,
    file: UploadFile = File(...),
    session_id: Optional[str] = Query(None, description="关联的 Session ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    上传文件到工作区

    会自动：
    1. 验证配额
    2. 记录审计日志
    3. 注册文件索引
    """
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    if not workspace.is_active:
        raise HTTPException(status_code=400, detail="Workspace is not active")

    # 读取文件内容
    content = await file.read()
    file_size = len(content)

    # 检查配额
    if not await service.check_quota(workspace, file_size):
        raise HTTPException(
            status_code=413,
            detail="Storage quota exceeded"
        )

    # 构建相对路径
    relative_path = f"uploads/{file.filename}"

    # 确保目录存在
    abs_path = os.path.join(workspace.root_path, "uploads")
    os.makedirs(abs_path, exist_ok=True)

    # 写入文件
    file_path = os.path.join(abs_path, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # 注册文件
    workspace_file = await service.register_file(
        workspace=workspace,
        filename=file.filename,
        relative_path=relative_path,
        file_size=file_size,
        mime_type=file.content_type,
        session_id=session_id,
        source_type="upload",
    )

    # 记录审计日志
    await service.log_action(
        workspace=workspace,
        action="upload",
        file_path=relative_path,
        user_id=current_user.id,
        file_size=file_size,
        success=True,
    )

    logger.info(
        f"File uploaded: {file.filename} to workspace {workspace_id}"
    )

    return {
        "id": workspace_file.id,
        "filename": workspace_file.filename,
        "relative_path": workspace_file.relative_path,
        "file_size": workspace_file.file_size,
        "absolute_path": workspace_file.absolute_path,
    }


@router.get("/{workspace_id}/files/{file_id}")
async def download_file(
    workspace_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载工作区中的文件"""
    from fastapi.responses import FileResponse

    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询文件
    result = await db.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.id == file_id,
            WorkspaceFile.workspace_id == workspace_id,
        )
    )
    workspace_file = result.scalar_one_or_none()

    if not workspace_file:
        raise HTTPException(status_code=404, detail="File not found")

    # 验证文件存在
    if not os.path.exists(workspace_file.absolute_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # 记录审计日志
    await service.log_action(
        workspace=workspace,
        action="download",
        file_path=workspace_file.relative_path,
        user_id=current_user.id,
        file_size=workspace_file.file_size,
        success=True,
    )

    return FileResponse(
        path=workspace_file.absolute_path,
        filename=workspace_file.filename,
        media_type=workspace_file.mime_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename={workspace_file.filename}",
        },
    )


@router.delete("/{workspace_id}/files/{file_id}")
async def delete_file(
    workspace_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除工作区中的文件"""
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询文件
    result = await db.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.id == file_id,
            WorkspaceFile.workspace_id == workspace_id,
        )
    )
    workspace_file = result.scalar_one_or_none()

    if not workspace_file:
        raise HTTPException(status_code=404, detail="File not found")

    # 删除文件
    file_path = workspace_file.absolute_path
    if os.path.exists(file_path):
        os.remove(file_path)

    # 更新配额
    await service.update_storage_usage(
        workspace, -workspace_file.file_size
    )

    # 从数据库删除
    await db.delete(workspace_file)
    await db.commit()

    # 记录审计日志
    await service.log_action(
        workspace=workspace,
        action="delete",
        file_path=workspace_file.relative_path,
        user_id=current_user.id,
        file_size=workspace_file.file_size,
        success=True,
    )

    logger.info(f"File deleted: {file_id} from workspace {workspace_id}")

    return {"message": "File deleted"}


@router.get("/{workspace_id}/audit-logs")
async def get_audit_logs(
    workspace_id: str,
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取工作区审计日志"""
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 查询审计日志
    result = await db.execute(
        select(WorkspaceAuditLog)
        .where(WorkspaceAuditLog.workspace_id == workspace_id)
        .order_by(WorkspaceAuditLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "file_path": log.file_path,
                "file_size": log.file_size,
                "success": log.success,
                "user_id": log.user_id,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    }
