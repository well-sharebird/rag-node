"""
Workspace 工作区服务

提供工作区管理、文件操作、路径验证、配额检查等能力
"""
import logging
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from packages.agent.models.workspace import (
    Workspace,
    WorkspaceFile,
    WorkspaceAuditLog,
)
from packages.agent.models.runtime import AgentRuntime
from packages.core.system.models.user import User

logger = logging.getLogger(__name__)


class WorkspaceService:
    """
    工作区服务

    提供工作区生命周期管理和文件操作
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_workspace_root = os.environ.get(
            "WORKSPACE_ROOT", "/workspace"
        )

    async def get_or_create_workspace(
        self,
        user: User,
        tenant_id: Optional[str] = None,
    ) -> Workspace:
        """
        获取或创建工作区

        每个用户有且仅有一个工作区
        """
        # 尝试获取现有工作区
        result = await self.db.execute(
            select(Workspace).where(
                Workspace.user_id == user.id,
                Workspace.tenant_id == tenant_id,
            )
        )
        workspace = result.scalar_one_or_none()

        if workspace:
            return workspace

        # 创建新工作区
        root_path = os.path.join(
            self.base_workspace_root, "users", str(user.id)
        )

        # 确保目录存在
        os.makedirs(root_path, exist_ok=True)

        workspace = Workspace(
            user_id=user.id,
            tenant_id=tenant_id,
            root_path=root_path,
            storage_quota_bytes=10 * 1024 * 1024 * 1024,  # 10GB
        )

        self.db.add(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)

        logger.info(
            f"Workspace created for user {user.id}: {root_path}"
        )

        return workspace

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """获取工作区"""
        result = await self.db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_user_workspace(
        self,
        user_id: int,
        tenant_id: Optional[str] = None,
    ) -> Optional[Workspace]:
        """获取用户的工作区"""
        result = await self.db.execute(
            select(Workspace).where(
                Workspace.user_id == user_id,
                Workspace.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_storage_usage(
        self,
        workspace: Workspace,
        delta_bytes: int,
    ) -> None:
        """更新存储使用量"""
        workspace.storage_used_bytes = max(
            0, workspace.storage_used_bytes + delta_bytes
        )
        await self.db.commit()

    def resolve_path(
        self,
        workspace: Workspace,
        requested_path: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        解析文件路径，防止越权访问

        安全措施：
        1. 规范化路径 (消除 ../)
        2. 验证路径在 workspace 根目录内
        3. 检查符号链接
        4. 可选：限定在特定 session 目录
        """
        # 规范化请求的路径
        safe_name = os.path.basename(requested_path)
        rel_path = os.path.normpath(requested_path)

        # 如果是绝对路径，尝试转换为相对路径
        if os.path.isabs(rel_path):
            try:
                rel_path = os.path.relpath(rel_path, workspace.root_path)
            except ValueError:
                raise SecurityError(
                    f"Path traversal detected: {requested_path}"
                )

        # 构建完整路径
        full_path = os.path.normpath(
            os.path.join(workspace.root_path, rel_path)
        )

        # 验证路径在 workspace 根目录内
        if not full_path.startswith(workspace.root_path):
            raise SecurityError(
                f"Path traversal detected: {requested_path}. "
                f"Resolved to: {full_path}"
            )

        # 如果指定了 session_id，进一步限制在 session 目录
        if session_id:
            session_dir = os.path.join(
                workspace.root_path, "sessions", session_id
            )
            if not full_path.startswith(session_dir):
                raise SecurityError(
                    f"Session boundary violation: {full_path}"
                )

        # 检查符号链接
        if os.path.islink(full_path):
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(workspace.root_path):
                raise SecurityError(
                    f"Symlink escape detected: {real_path}"
                )

        return full_path

    async def check_quota(
        self,
        workspace: Workspace,
        required_bytes: int,
    ) -> bool:
        """检查是否有足够配额"""
        return workspace.check_quota(required_bytes)

    async def register_file(
        self,
        workspace: Workspace,
        filename: str,
        relative_path: str,
        file_size: int,
        mime_type: Optional[str] = None,
        runtime_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source_type: str = "upload",
    ) -> WorkspaceFile:
        """
        注册文件到工作区索引
        """
        # 检查配额
        if not await self.check_quota(workspace, file_size):
            raise QuotaExceededError(
                f"Workspace quota exceeded. Required: {file_size} bytes"
            )

        # 计算文件哈希 (可选，由调用者传入)
        file_hash = None  # 可以在上传时计算

        workspace_file = WorkspaceFile(
            workspace_id=workspace.id,
            runtime_id=runtime_id,
            session_id=session_id,
            filename=filename,
            relative_path=relative_path,
            absolute_path=os.path.join(workspace.root_path, relative_path),
            file_size=file_size,
            mime_type=mime_type,
            file_hash=file_hash,
            source_type=source_type,
            is_sandbox_generated=(source_type == "generated"),
        )

        self.db.add(workspace_file)

        # 更新配额使用
        await self.update_storage_usage(workspace, file_size)

        await self.db.commit()
        await self.db.refresh(workspace_file)

        return workspace_file

    async def log_action(
        self,
        workspace: Workspace,
        action: str,
        file_path: str,
        user_id: Optional[int] = None,
        runtime_id: Optional[str] = None,
        session_id: Optional[str] = None,
        file_size: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> WorkspaceAuditLog:
        """记录审计日志"""
        log_entry = WorkspaceAuditLog(
            workspace_id=workspace.id,
            user_id=user_id,
            runtime_id=runtime_id,
            session_id=session_id,
            action=action,
            file_path=file_path,
            file_size=file_size,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(log_entry)
        await self.db.commit()

        return log_entry

    async def delete_workspace(self, workspace: Workspace) -> None:
        """
        删除工作区

        会删除所有关联的文件和目录
        """
        import shutil

        workspace.status = "deleted"

        # 删除文件系统目录
        if os.path.exists(workspace.root_path):
            shutil.rmtree(workspace.root_path)
            logger.info(f"Workspace directory deleted: {workspace.root_path}")

        await self.db.commit()

        logger.info(f"Workspace deleted: {workspace.id}")

    async def cleanup_inactive_workspaces(
        self,
        days_threshold: int = 90,
    ) -> int:
        """
        清理长期不活跃的工作区

        返回清理的工作区数量
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)

        result = await self.db.execute(
            select(Workspace).where(
                Workspace.status == "active",
                Workspace.updated_at < cutoff_date,
            )
        )
        workspaces = result.scalars().all()

        count = 0
        for workspace in workspaces:
            # 检查是否真的没有活动
            file_result = await self.db.execute(
                select(func.count(WorkspaceFile.id)).where(
                    WorkspaceFile.workspace_id == workspace.id,
                    WorkspaceFile.created_at > cutoff_date,
                )
            )
            file_count = file_result.scalar()

            if file_count == 0:
                await self.delete_workspace(workspace)
                count += 1

        return count


class SecurityError(Exception):
    """安全违规异常"""
    pass


class QuotaExceededError(Exception):
    """配额超限异常"""
    pass
