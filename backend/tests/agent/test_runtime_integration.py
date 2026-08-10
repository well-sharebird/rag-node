"""
Runtime 集成测试

测试 Runtime 生命周期管理功能
"""
import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.system.models.user import User
from packages.agent.models.agent import AgentConfig
from packages.agent.models.workspace import Workspace
from packages.agent.models.runtime import AgentRuntime, AgentRuntimeEvent
from packages.agent.services.runtime_service import RuntimeService
from packages.agent.services.workspace_service import WorkspaceService
from packages.agent.schemas.manifest import (
    AgentManifest,
    ManifestModelConfig,
    ManifestWorkspaceConfig,
    ManifestSecurityPolicy,
    ManifestMemoryConfig,
)


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
async def test_agent(db_session: AsyncSession, test_user: User) -> AgentConfig:
    """创建测试 Agent"""
    agent = AgentConfig(
        name=f"Test Agent {os.urandom(4).hex()}",
        user_id=test_user.id,
        system_prompt="You are a helpful assistant.",
        agent_type="single",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest.fixture
async def test_workspace(
    db_session: AsyncSession,
    test_user: User,
) -> Workspace:
    """创建测试工作区"""
    workspace = Workspace(
        user_id=test_user.id,
        root_path=f"/tmp/test_workspace_{os.urandom(4).hex()}",
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.fixture
def runtime_service(db_session: AsyncSession) -> RuntimeService:
    """创建 Runtime 服务"""
    return RuntimeService(db_session)


@pytest.fixture
def test_manifest(test_agent: AgentConfig) -> AgentManifest:
    """创建测试 Manifest"""
    return AgentManifest(
        agent_id=str(test_agent.id),
        name=test_agent.name,
        system_prompt=test_agent.system_prompt,
        workspace=ManifestWorkspaceConfig(
            root_path="/tmp/test_workspace"
        ),
        security_policy=ManifestSecurityPolicy(),
        memory=ManifestMemoryConfig(),
    )


@pytest.mark.asyncio
async def test_create_runtime(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试创建 Runtime"""
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )

    assert runtime is not None
    assert runtime.agent_id == str(test_agent.id)
    assert runtime.workspace_id == test_workspace.id
    assert runtime.status == "initializing"
    assert runtime.sandbox_type == "nsjail"


@pytest.mark.asyncio
async def test_runtime_lifecycle(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试 Runtime 完整生命周期"""
    # 创建
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )
    assert runtime.status == "initializing"

    # 启动
    runtime = await runtime_service.start_runtime(runtime.id)
    assert runtime.status == "running"
    assert runtime.started_at is not None

    # 休眠
    runtime = await runtime_service.sleep_runtime(runtime.id)
    assert runtime.status == "sleeping"

    # 唤醒
    runtime = await runtime_service.wake_runtime(runtime.id)
    assert runtime.status == "running"

    # 停止
    runtime = await runtime_service.stop_runtime(runtime.id)
    assert runtime.status == "stopped"
    assert runtime.stopped_at is not None


@pytest.mark.asyncio
async def test_runtime_events(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试 Runtime 事件记录"""
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )

    # 启动后检查事件
    await runtime_service.start_runtime(runtime.id)

    result = await db_session.execute(
        select(AgentRuntimeEvent).where(
            AgentRuntimeEvent.runtime_id == runtime.id
        )
    )
    events = result.scalars().all()

    assert len(events) >= 2  # created + started
    event_types = [e.event_type for e in events]
    assert "created" in event_types
    assert "started" in event_types


@pytest.mark.asyncio
async def test_runtime_idle_sleep(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试空闲自动休眠"""
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )
    await runtime_service.start_runtime(runtime.id)

    # 模拟空闲时间
    runtime.last_active_at = datetime.utcnow()
    runtime.idle_timeout_seconds = 1  # 1 秒超时
    await db_session.commit()

    # 等待后检查是否自动休眠
    await asyncio.sleep(2)

    count = await runtime_service.check_idle_and_sleep()
    # 注意：实际测试中需要验证 runtime 状态变化


@pytest.mark.asyncio
async def test_resource_usage_update(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试资源使用更新"""
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )

    # 更新资源使用
    await runtime_service.update_resource_usage(
        runtime.id,
        {
            "cpu_percent": 25.5,
            "memory_mb": 64,
            "disk_mb": 10,
        },
    )

    await db_session.refresh(runtime)
    assert runtime.resource_usage["cpu_percent"] == 25.5
    assert runtime.resource_usage["memory_mb"] == 64


@pytest.mark.asyncio
async def test_get_runtime_sessions(
    db_session: AsyncSession,
    runtime_service: RuntimeService,
    test_agent: AgentConfig,
    test_workspace: Workspace,
    test_manifest: AgentManifest,
):
    """测试获取 Runtime 下的 Sessions"""
    runtime = await runtime_service.create_runtime(
        agent=test_agent,
        workspace=test_workspace,
        manifest=test_manifest,
    )

    sessions = await runtime_service.get_runtime_sessions(runtime.id)
    assert sessions is not None
    assert isinstance(sessions, list)


# 导入 os 模块
import os
