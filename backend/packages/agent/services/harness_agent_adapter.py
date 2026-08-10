"""
Harness Agent Adapter

将 Harness Engine 集成到现有 Agent 执行流程的适配层
"""
import logging
from typing import Optional, Dict, Any, AsyncGenerator, List
from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.services.harness_engine_service import (
    HarnessEngineService,
    HarnessExecutionRequest,
)
from packages.agent.runtime_engine.orchestration import (
    OrchestrationConfig,
    OrchestrationMode,
    WorkerAgent,
)
from packages.agent.services.workspace_service import WorkspaceService
from packages.agent.services.runtime_service import RuntimeService
from packages.core.system.models.user import User

logger = logging.getLogger(__name__)


class HarnessAgentAdapter:
    """
    Harness Agent 适配器

    将 Harness Engine 集成到现有 Agent 执行流程：
    1. 使用 Workspace 实现用户隔离
    2. 使用 Runtime 管理 Agent 运行环境
    3. 使用 Harness 四层引擎执行
    4. 支持沙箱代码执行
    """

    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self._harness_service: Optional[HarnessEngineService] = None
        self._workspace_service: Optional[WorkspaceService] = None
        self._runtime_service: Optional[RuntimeService] = None
        self._workspace = None
        self._runtime = None

    async def _ensure_workspace(self) -> None:
        """确保用户工作区存在"""
        if self._workspace_service is None:
            self._workspace_service = WorkspaceService(self.db)

        if self._workspace is None:
            self._workspace = await self._workspace_service.get_or_create_workspace(self.user)
            logger.info(f"Workspace ensured for user {self.user.id}: {self._workspace.root_path}")

    async def _ensure_runtime(self, agent_id: str) -> None:
        """确保 Runtime 存在"""
        if self._runtime_service is None:
            self._runtime_service = RuntimeService(self.db)

        if self._runtime is None:
            # 创建 Runtime
            from packages.agent.models.agent import AgentConfig
            from sqlalchemy import select

            result = await self.db.execute(
                select(AgentConfig).where(AgentConfig.id == agent_id)
            )
            agent = result.scalar_one_or_none()

            if agent:
                from packages.agent.schemas.manifest import (
                    AgentManifest,
                    ManifestWorkspaceConfig,
                    ManifestSecurityPolicy,
                    ManifestMemoryConfig,
                )

                manifest = AgentManifest(
                    agent_id=agent_id,
                    name=agent.name,
                    system_prompt=agent.system_prompt,
                    workspace=ManifestWorkspaceConfig(
                        root_path=self._workspace.root_path,
                        session_isolation=True,
                    ),
                    security_policy=ManifestSecurityPolicy(
                        allowed_tools=agent.enabled_skills or [],
                        allow_network_access=False,
                        max_code_execution_time_seconds=30,
                    ),
                    memory=ManifestMemoryConfig(
                        memory_type=agent.memory_type,
                        ttl_hours=agent.memory_ttl_hours,
                        max_turns=agent.max_memory_turns,
                    ),
                )

                self._runtime = await self._runtime_service.create_runtime(
                    agent=agent,
                    workspace=self._workspace,
                    manifest=manifest,
                    created_by=self.user.id,
                )

                # 启动 Runtime
                await self._runtime_service.start_runtime(self._runtime.id)
                logger.info(f"Runtime created and started: {self._runtime.id}")

    async def _get_harness_service(self) -> HarnessEngineService:
        """获取 Harness 引擎服务"""
        if self._harness_service is None:
            self._harness_service = HarnessEngineService(self.db)
        return self._harness_service

    async def execute_with_harness(
        self,
        agent_id: str,
        query: str,
        session_id: str,
        use_multi_agent: bool = False,
        orchestration_mode: str = "supervisor",
        workers: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        使用 Harness Engine 执行 Agent 请求

        Args:
            agent_id: Agent ID
            query: 用户查询
            session_id: 会话 ID
            use_multi_agent: 是否使用多 Agent 协作
            orchestration_mode: 编排模式
            workers: Worker Agent 配置

        Yields:
            流式输出 token
        """
        try:
            # 确保 Workspace 和 Runtime
            await self._ensure_workspace()
            await self._ensure_runtime(agent_id)

            # 获取 Harness 服务
            harness_service = await self._get_harness_service()

            # 构建编排配置
            orchestration_config = None
            if use_multi_agent and workers:
                orchestration_config = OrchestrationConfig(
                    mode=OrchestrationMode(orchestration_mode),
                    workers=[
                        WorkerAgent(
                            agent_id=w["agent_id"],
                            role=w["role"],
                            priority=w.get("priority", 0),
                        )
                        for w in workers
                    ],
                )

            # 构建执行请求
            request = HarnessExecutionRequest(
                runtime_id=self._runtime.id,
                session_id=session_id,
                user_id=self.user.id,
                user_input=query,
                stream=True,
            )

            # 流式执行
            async for token in harness_service.execute_stream(
                request=request,
                orchestration_config=orchestration_config,
            ):
                yield token

            logger.info(
                f"Harness execution completed | agent={agent_id} "
                f"session={session_id} mode={orchestration_mode}"
            )

        except Exception as e:
            logger.error(f"Harness execution failed: {e}")
            yield f"[Error: {str(e)}]"

    async def execute_code_in_sandbox(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        在沙箱中执行代码

        Args:
            code: 代码
            language: 编程语言
            timeout_seconds: 超时时间

        Returns:
            执行结果
        """
        from packages.agent.sandbox.nsjail import execute_code_in_sandbox

        await self._ensure_workspace()

        result = await execute_code_in_sandbox(
            code=code,
            language=language,
            workspace_path=self._workspace.root_path,
            timeout_seconds=timeout_seconds,
        )

        # 记录审计日志
        if self._workspace_service:
            await self._workspace_service.log_action(
                workspace=self._workspace,
                action="execute",
                file_path=f"sandbox:{language}",
                user_id=self.user.id,
                success=(result.exit_code == 0),
            )

        return {
            "success": result.exit_code == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        }

    async def get_workspace_info(self) -> Dict[str, Any]:
        """获取用户工作区信息"""
        await self._ensure_workspace()

        return {
            "id": self._workspace.id,
            "root_path": self._workspace.root_path,
            "storage_quota_bytes": self._workspace.storage_quota_bytes,
            "storage_used_bytes": self._workspace.storage_used_bytes,
            "storage_used_percent": self._workspace.storage_used_percent,
            "status": self._workspace.status,
        }

    async def cleanup(self) -> None:
        """清理资源"""
        if self._harness_service:
            self._harness_service.cleanup()

        if self._runtime and self._runtime_service:
            # 可选：休眠或停止 Runtime
            # await self._runtime_service.sleep_runtime(self._runtime.id)
            pass

        logger.info("HarnessAgentAdapter cleaned up")
