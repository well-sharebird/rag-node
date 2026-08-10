"""
Agent Runtime 服务

提供 Runtime 生命周期管理：创建、启动、停止、休眠、唤醒
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.models.runtime import (
    AgentRuntime,
    AgentRuntimeEvent,
)
from packages.agent.models.session import AgentSession
from packages.agent.models.workspace import Workspace
from packages.agent.models.agent import AgentConfig
from packages.agent.schemas.manifest import AgentManifest

logger = logging.getLogger(__name__)


class RuntimeService:
    """
    Runtime 服务

    管理 Agent 运行时的完整生命周期
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.sandbox_manager = None  # 懒加载

    async def create_runtime(
        self,
        agent: AgentConfig,
        workspace: Workspace,
        manifest: Optional[AgentManifest] = None,
        created_by: Optional[int] = None,
    ) -> AgentRuntime:
        """
        创建 Runtime

        1. 验证 Manifest 配置
        2. 创建 Runtime 记录
        3. 初始化沙箱环境
        """
        # 如果没有传入 manifest，从 AgentConfig 构建
        if manifest is None:
            manifest = self._build_manifest_from_agent(agent)

        # 验证 Manifest
        self._validate_manifest(manifest)

        # 创建 Runtime
        runtime = AgentRuntime(
            agent_id=agent.id,
            workspace_id=workspace.id,
            created_by=created_by,
            manifest=manifest.model_dump(),
            sandbox_type="nsjail",  # 默认使用 nsjail
            sandbox_config={
                "memory_mb": 128,
                "vcpu_count": 1,
                "timeout_seconds": 30,
                "network_enabled": manifest.security_policy.allow_network_access,
            },
            status="initializing",
            idle_timeout_seconds=900,  # 15 分钟
            auto_sleep_enabled=True,
        )

        self.db.add(runtime)
        await self.db.commit()
        await self.db.refresh(runtime)

        # 记录事件
        await self._log_event(
            runtime,
            "created",
            {"manifest_version": manifest.version},
        )

        logger.info(f"Runtime created: {runtime.id} for agent {agent.id}")

        return runtime

    async def start_runtime(self, runtime_id: str) -> AgentRuntime:
        """
        启动 Runtime

        1. 创建沙箱环境
        2. 更新状态为 running
        3. 记录启动事件
        """
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            raise RuntimeError(f"Runtime not found: {runtime_id}")

        if runtime.status == "running":
            logger.info(f"Runtime already running: {runtime_id}")
            return runtime

        # 创建沙箱
        sandbox_id = await self._create_sandbox(runtime)

        runtime.sandbox_id = sandbox_id
        runtime.status = "running"
        runtime.started_at = datetime.utcnow()
        runtime.last_active_at = datetime.utcnow()
        runtime.start_count += 1
        runtime.last_started_at = datetime.utcnow()

        await self.db.commit()

        await self._log_event(
            runtime,
            "started",
            {"sandbox_id": sandbox_id},
        )

        logger.info(f"Runtime started: {runtime_id}, sandbox: {sandbox_id}")

        return runtime

    async def stop_runtime(self, runtime_id: str) -> AgentRuntime:
        """停止 Runtime"""
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            raise RuntimeError(f"Runtime not found: {runtime_id}")

        if runtime.status not in ["running", "sleeping"]:
            logger.info(f"Runtime not running: {runtime_id}")
            return runtime

        # 停止沙箱
        if runtime.sandbox_id:
            await self._stop_sandbox(runtime.sandbox_id)

        runtime.status = "stopped"
        runtime.stopped_at = datetime.utcnow()

        await self.db.commit()

        await self._log_event(runtime, "stopped", {})

        logger.info(f"Runtime stopped: {runtime_id}")

        return runtime

    async def sleep_runtime(self, runtime_id: str) -> AgentRuntime:
        """
        休眠 Runtime

        保存状态，释放资源，保留数据
        """
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            raise RuntimeError(f"Runtime not found: {runtime_id}")

        if runtime.status != "running":
            return runtime

        # 保存检查点
        await self._save_checkpoint(runtime)

        # 停止沙箱但保留数据
        if runtime.sandbox_id:
            await self._stop_sandbox(runtime.sandbox_id, preserve_data=True)

        runtime.status = "sleeping"

        await self.db.commit()

        await self._log_event(runtime, "slept", {})

        logger.info(f"Runtime slept: {runtime_id}")

        return runtime

    async def wake_runtime(self, runtime_id: str) -> AgentRuntime:
        """
        唤醒 Runtime

        从休眠状态恢复
        """
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            raise RuntimeError(f"Runtime not found: {runtime_id}")

        if runtime.status != "sleeping":
            return runtime

        # 恢复沙箱
        sandbox_id = await self._restore_sandbox(runtime)
        runtime.sandbox_id = sandbox_id
        runtime.status = "running"
        runtime.last_active_at = datetime.utcnow()

        await self.db.commit()

        await self._log_event(runtime, "woken", {"sandbox_id": sandbox_id})

        logger.info(f"Runtime woken: {runtime_id}")

        return runtime

    async def check_idle_and_sleep(self) -> int:
        """
        检查空闲的 Runtime 并自动休眠

        返回休眠的 Runtime 数量
        """
        result = await self.db.execute(
            select(AgentRuntime).where(
                AgentRuntime.status == "running",
                AgentRuntime.auto_sleep_enabled == True,
            )
        )
        runtimes = result.scalars().all()

        count = 0
        for runtime in runtimes:
            if runtime.should_sleep():
                await self.sleep_runtime(runtime.id)
                count += 1

        return count

    async def get_runtime(self, runtime_id: str) -> Optional[AgentRuntime]:
        """获取 Runtime 详情"""
        return await self._get_runtime(runtime_id)

    async def get_runtime_sessions(
        self,
        runtime_id: str,
    ) -> list[AgentSession]:
        """获取 Runtime 下的所有 Session"""
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            return []

        # 通过关系加载
        await self.db.refresh(runtime)
        return runtime.sessions

    async def update_resource_usage(
        self,
        runtime_id: str,
        resource_data: Dict[str, Any],
    ) -> None:
        """更新资源使用数据"""
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            return

        runtime.resource_usage = {
            **runtime.resource_usage,
            **resource_data,
            "last_updated": datetime.utcnow().isoformat(),
        }

        await self.db.commit()

    async def delete_runtime(self, runtime_id: str) -> None:
        """删除 Runtime"""
        runtime = await self._get_runtime(runtime_id)
        if not runtime:
            return

        # 先停止
        if runtime.status in ["running", "sleeping"]:
            await self.stop_runtime(runtime_id)

        # 删除记录 (级联删除 Sessions)
        await self.db.delete(runtime)
        await self.db.commit()

        logger.info(f"Runtime deleted: {runtime_id}")

    # ========== 内部方法 ==========

    async def _get_runtime(
        self,
        runtime_id: str,
    ) -> Optional[AgentRuntime]:
        """获取 Runtime"""
        result = await self.db.execute(
            select(AgentRuntime).where(AgentRuntime.id == runtime_id)
        )
        return result.scalar_one_or_none()

    def _build_manifest_from_agent(
        self,
        agent: AgentConfig,
    ) -> AgentManifest:
        """从 AgentConfig 构建 Manifest"""
        from packages.agent.schemas.manifest import (
            AgentManifest,
            ManifestModelConfig,
            ManifestWorkspaceConfig,
            ManifestSecurityPolicy,
            ManifestMemoryConfig,
        )

        return AgentManifest(
            agent_id=str(agent.id),
            name=agent.name,
            version=agent.current_version,
            description=agent.description,
            model_config=ManifestModelConfig(
                **agent.default_model_config
            ) if agent.default_model_config else ManifestModelConfig(),
            system_prompt=agent.system_prompt,
            enabled_tools=agent.enabled_skills or [],
            mcp_servers=agent.mcp_servers or [],
            workspace=ManifestWorkspaceConfig(
                root_path=f"/workspace/agents/{agent.id}"
            ),
            security_policy=ManifestSecurityPolicy(
                allowed_tools=agent.enabled_skills or [],
            ),
            memory=ManifestMemoryConfig(
                memory_type=agent.memory_type,
                ttl_hours=agent.memory_ttl_hours,
                max_turns=agent.max_memory_turns,
            ),
        )

    def _validate_manifest(self, manifest: AgentManifest) -> None:
        """验证 Manifest 配置"""
        # 基本验证由 Pydantic 完成
        # 这里可以添加业务逻辑验证
        pass

    async def _create_sandbox(self, runtime: AgentRuntime) -> str:
        """
        创建沙箱环境

        返回沙箱 ID
        """
        # TODO: 集成 nsjail 或 Firecracker
        # 目前返回一个模拟的 ID
        sandbox_id = f"sandbox-{uuid.uuid4().hex[:12]}"
        logger.info(f"Sandbox created: {sandbox_id}")
        return sandbox_id

    async def _stop_sandbox(
        self,
        sandbox_id: str,
        preserve_data: bool = False,
    ) -> None:
        """停止沙箱"""
        logger.info(f"Sandbox stopped: {sandbox_id}, preserve={preserve_data}")
        # TODO: 实现沙箱停止逻辑

    async def _restore_sandbox(
        self,
        runtime: AgentRuntime,
    ) -> str:
        """恢复沙箱"""
        # TODO: 实现沙箱恢复逻辑
        return f"sandbox-{uuid.uuid4().hex[:12]}"

    async def _save_checkpoint(self, runtime: AgentRuntime) -> None:
        """保存运行时检查点"""
        # TODO: 实现检查点保存逻辑
        logger.info(f"Checkpoint saved for runtime: {runtime.id}")

    async def _log_event(
        self,
        runtime: AgentRuntime,
        event_type: str,
        event_data: Optional[Dict[str, Any]],
    ) -> None:
        """记录事件日志"""
        event = AgentRuntimeEvent(
            runtime_id=runtime.id,
            event_type=event_type,
            event_data=event_data,
        )
        self.db.add(event)
        await self.db.commit()
