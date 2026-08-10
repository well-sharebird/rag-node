"""
Workspace 集成测试

测试工作区 CRUD 和文件操作功能
"""
import pytest
import os
import tempfile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.system.models.user import User
from packages.agent.models.workspace import Workspace, WorkspaceFile, WorkspaceAuditLog
from packages.agent.services.workspace_service import WorkspaceService


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """创建测试用户"""
    user = User(
        username=f"test_user_{os.urandom(4).hex()}",
        email=f"test_{os.urandom(4).hex()}@example.com",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def workspace_service(db_session: AsyncSession) -> WorkspaceService:
    """创建工作区服务"""
    # 使用临时目录作为工作区根
    with tempfile.TemporaryDirectory() as tmpdir:
        service = WorkspaceService(db_session)
        service.base_workspace_root = tmpdir
        yield service


@pytest.mark.asyncio
async def test_get_or_create_workspace(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试获取或创建工作区"""
    # 第一次调用应该创建工作区
    workspace = await workspace_service.get_or_create_workspace(test_user)

    assert workspace is not None
    assert workspace.user_id == test_user.id
    assert os.path.exists(workspace.root_path)
    assert workspace.status == "active"
    assert workspace.storage_quota_bytes == 10 * 1024 * 1024 * 1024  # 10GB

    # 第二次调用应该返回现有工作区
    workspace2 = await workspace_service.get_or_create_workspace(test_user)
    assert workspace2.id == workspace.id


@pytest.mark.asyncio
async def test_workspace_file_operations(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试工作区文件操作"""
    # 创建工作区
    workspace = await workspace_service.get_or_create_workspace(test_user)

    # 上传文件
    file_content = b"Hello, World!"
    filename = "test_file.txt"
    relative_path = f"uploads/{filename}"

    # 确保目录存在
    upload_dir = os.path.join(workspace.root_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # 写入文件
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)

    # 注册文件
    workspace_file = await workspace_service.register_file(
        workspace=workspace,
        filename=filename,
        relative_path=relative_path,
        file_size=len(file_content),
        mime_type="text/plain",
        source_type="upload",
    )

    assert workspace_file is not None
    assert workspace_file.filename == filename
    assert workspace_file.file_size == len(file_content)

    # 验证配额更新
    await db_session.refresh(workspace)
    assert workspace.storage_used_bytes == len(file_content)


@pytest.mark.asyncio
async def test_workspace_path_validation(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试路径验证（防止路径遍历攻击）"""
    workspace = await workspace_service.get_or_create_workspace(test_user)

    # 合法路径应该通过
    safe_path = workspace_service.resolve_path(workspace, "uploads/test.txt")
    assert safe_path.startswith(workspace.root_path)

    # 路径遍历攻击应该被阻止
    with pytest.raises(Exception) as exc_info:
        workspace_service.resolve_path(workspace, "../../../etc/passwd")
    assert "Path traversal" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workspace_quota_check(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试配额检查"""
    workspace = await workspace_service.get_or_create_workspace(test_user)

    # 小文件应该通过
    has_quota = await workspace_service.check_quota(workspace, 1024)
    assert has_quota is True

    # 超大文件应该失败
    has_quota = await workspace_service.check_quota(
        workspace, workspace.storage_quota_bytes + 1
    )
    assert has_quota is False


@pytest.mark.asyncio
async def test_workspace_audit_logging(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试审计日志"""
    workspace = await workspace_service.get_or_create_workspace(test_user)

    # 记录审计日志
    await workspace_service.log_action(
        workspace=workspace,
        action="upload",
        file_path="uploads/test.txt",
        user_id=test_user.id,
        file_size=1024,
        success=True,
    )

    # 验证日志记录
    result = await db_session.execute(
        select(WorkspaceAuditLog).where(
            WorkspaceAuditLog.workspace_id == workspace.id
        )
    )
    logs = result.scalars().all()

    assert len(logs) >= 1
    assert logs[-1].action == "upload"
    assert logs[-1].user_id == test_user.id


@pytest.mark.asyncio
async def test_workspace_delete(
    db_session: AsyncSession,
    workspace_service: WorkspaceService,
    test_user: User,
):
    """测试删除工作区"""
    workspace = await workspace_service.get_or_create_workspace(test_user)
    workspace_id = workspace.id
    root_path = workspace.root_path

    # 删除工作区
    await workspace_service.delete_workspace(workspace)

    # 验证目录已删除
    assert not os.path.exists(root_path)

    # 验证数据库记录
    result = await db_session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    deleted_workspace = result.scalar_one_or_none()
    assert deleted_workspace is not None
    assert deleted_workspace.status == "deleted"
