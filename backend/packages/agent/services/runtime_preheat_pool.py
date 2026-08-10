"""
Runtime 预热池管理器

实现 Runtime 的预热和快速启动能力：
1. 预创建 Runtime 池
2. 快速分配给新用户
3. 自动回收空闲 Runtime
4. 支持 Copy-on-Write Fork
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.models.runtime import AgentRuntime, AgentRuntimeEvent
from packages.agent.models.workspace import Workspace
from packages.agent.services.runtime_service import RuntimeService

logger = logging.getLogger(__name__)


class PoolStrategy(str, Enum):
    """预热池策略"""
    FIFO = "fifo"  # 先进先出
    LRU = "lru"  # 最近最少使用
    RANDOM = "random"  # 随机


@dataclass
class PoolConfig:
    """预热池配置"""
    min_size: int = 2
    max_size: int = 10
    idle_timeout_seconds: int = 300  # 5 分钟
    health_check_interval: int = 60  # 1 分钟
    strategy: PoolStrategy = PoolStrategy.LRU
    preheat_on_startup: bool = True


@dataclass
class PoolStats:
    """池统计信息"""
    total_size: int
    available: int
    in_use: int
    warm: int  # 已预热的数量
    cold: int  # 需要冷启动的数量
    avg_start_time_ms: float


class RuntimePreheatPool:
    """
    Runtime 预热池

    核心能力：
    1. 预创建 Runtime 池，减少冷启动延迟
    2. 快速分配 Runtime 给新用户
    3. 自动回收空闲 Runtime
    4. 健康检查
    5. 支持 Copy-on-Write Fork (快速复制)
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[PoolConfig] = None,
    ):
        self.db = db
        self.config = config or PoolConfig()

        # 池状态
        self._pool: List[str] = []  # Runtime ID 列表
        self._in_use: set[str] = set()  # 使用中的 Runtime ID
        self._runtime_info: Dict[str, Dict[str, Any]] = {}  # Runtime 元信息

        # 统计信息
        self._total_created = 0
        self._total_allocated = 0
        self._start_times: List[float] = []  # 启动时间记录

        # 后台任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._auto_scale_task: Optional[asyncio.Task] = None

        # 服务
        self._runtime_service: Optional[RuntimeService] = None

    async def initialize(self) -> None:
        """
        初始化预热池

        1. 创建初始 Runtime
        2. 启动后台任务
        """
        logger.info(
            f"Initializing Runtime preheat pool | "
            f"min={self.config.min_size} max={self.config.max_size}"
        )

        self._runtime_service = RuntimeService(self.db)

        # 预热初始 Runtime
        if self.config.preheat_on_startup:
            await self._preheat_runtimes(self.config.min_size)

        # 启动后台任务
        self._health_check_task = asyncio.create_task(
            self._health_check_loop()
        )
        self._auto_scale_task = asyncio.create_task(
            self._auto_scale_loop()
        )

        logger.info("Runtime preheat pool initialized")

    async def shutdown(self) -> None:
        """关闭预热池"""
        # 取消后台任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._auto_scale_task:
            self._auto_scale_task.cancel()
            try:
                await self._auto_scale_task
            except asyncio.CancelledError:
                pass

        # 清理所有 Runtime
        await self.cleanup()

        logger.info("Runtime preheat pool shutdown complete")

    async def acquire(
        self,
        agent_id: str,
        workspace: Workspace,
        timeout_seconds: int = 30,
    ) -> AgentRuntime:
        """
        获取一个 Runtime

        优先从池中分配，如果池空则创建新的

        Args:
            agent_id: Agent ID
            workspace: 工作区
            timeout_seconds: 超时时间

        Returns:
            AgentRuntime: Runtime 实例
        """
        start_time = datetime.utcnow()

        # 尝试从池中获取
        runtime_id = await self._acquire_from_pool()

        if runtime_id:
            # 从池中获取成功
            runtime = await self._get_runtime(runtime_id)
            if runtime:
                logger.info(
                    f"Runtime acquired from pool | id={runtime_id} "
                    f"agent={agent_id}"
                )
                return runtime

        # 池空或获取失败，创建新的
        logger.info(f"Creating new Runtime | agent={agent_id}")
        runtime = await self._create_and_warm_runtime(agent_id, workspace)

        # 记录启动时间
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        self._start_times.append(duration)

        logger.info(
            f"Runtime created | id={runtime.id} duration={duration:.0f}ms"
        )

        return runtime

    async def release(self, runtime_id: str) -> None:
        """
        释放 Runtime 回池

        Args:
            runtime_id: Runtime ID
        """
        if runtime_id in self._in_use:
            self._in_use.remove(runtime_id)
            self._pool.append(runtime_id)

            # 更新最后使用时间
            self._runtime_info[runtime_id] = {
                **self._runtime_info.get(runtime_id, {}),
                "last_used": datetime.utcnow().isoformat(),
            }

            logger.info(f"Runtime released to pool | id={runtime_id}")

    async def cleanup(self) -> None:
        """清理池中所有 Runtime"""
        runtime_ids = list(self._pool) + list(self._in_use)

        for runtime_id in runtime_ids:
            try:
                if self._runtime_service:
                    await self._runtime_service.stop_runtime(runtime_id)
            except Exception as e:
                logger.error(f"Error stopping runtime {runtime_id}: {e}")

        self._pool.clear()
        self._in_use.clear()

        logger.info(f"Cleaned up {len(runtime_ids)} runtimes")

    async def get_stats(self) -> PoolStats:
        """获取池统计"""
        warm_count = 0
        cold_count = 0

        for runtime_id in self._pool:
            info = self._runtime_info.get(runtime_id, {})
            if info.get("warmed", False):
                warm_count += 1
            else:
                cold_count += 1

        avg_start_time = (
            sum(self._start_times) / len(self._start_times)
            if self._start_times else 0
        )

        return PoolStats(
            total_size=len(self._pool) + len(self._in_use),
            available=len(self._pool),
            in_use=len(self._in_use),
            warm=warm_count,
            cold=cold_count,
            avg_start_time_ms=avg_start_time,
        )

    async def fork_runtime(
        self,
        source_runtime_id: str,
        agent_id: str,
        workspace: Workspace,
    ) -> Optional[AgentRuntime]:
        """
        Copy-on-Write Fork: 快速复制 Runtime

        利用文件系统 CoW 特性，秒级复制 Runtime

        Args:
            source_runtime_id: 源 Runtime ID
            agent_id: 新 Agent ID
            workspace: 工作区

        Returns:
            AgentRuntime: 新的 Runtime 实例
        """
        logger.info(
            f"Forking Runtime | source={source_runtime_id} agent={agent_id}"
        )

        # 获取源 Runtime
        source_runtime = await self._get_runtime(source_runtime_id)
        if not source_runtime:
            logger.error(f"Source runtime not found: {source_runtime_id}")
            return None

        try:
            # 创建新的 Runtime 记录
            new_runtime = AgentRuntime(
                agent_id=agent_id,
                workspace_id=workspace.id,
                manifest=source_runtime.manifest,
                sandbox_type=source_runtime.sandbox_type,
                sandbox_config=source_runtime.sandbox_config,
                status="initializing",
            )

            self.db.add(new_runtime)
            await self.db.commit()
            await self.db.refresh(new_runtime)

            # TODO: 实现实际的 CoW 文件系统复制
            # 这里只是框架实现

            logger.info(
                f"Runtime forked | new_id={new_runtime.id} "
                f"source={source_runtime_id}"
            )

            return new_runtime

        except Exception as e:
            logger.error(f"Error forking runtime: {e}")
            return None

    # ========== 内部方法 ==========

    async def _acquire_from_pool(self) -> Optional[str]:
        """从池中获取一个 Runtime"""
        if not self._pool:
            return None

        # 根据策略选择
        if self.config.strategy == PoolStrategy.FIFO:
            runtime_id = self._pool.pop(0)
        elif self.config.strategy == PoolStrategy.LRU:
            # 选择最久未使用的
            runtime_id = self._find_lru()
            if runtime_id:
                self._pool.remove(runtime_id)
        else:  # RANDOM
            import random
            runtime_id = random.choice(self._pool)
            self._pool.remove(runtime_id)

        self._in_use.add(runtime_id)
        return runtime_id

    def _find_lru(self) -> Optional[str]:
        """查找最近最少使用的 Runtime"""
        if not self._pool:
            return None

        oldest_time = None
        oldest_id = None

        for runtime_id in self._pool:
            info = self._runtime_info.get(runtime_id, {})
            last_used = info.get("last_used")

            if last_used:
                if oldest_time is None or last_used < oldest_time:
                    oldest_time = last_used
                    oldest_id = runtime_id

        return oldest_id or self._pool[0]

    async def _create_and_warm_runtime(
        self,
        agent_id: str,
        workspace: Workspace,
    ) -> AgentRuntime:
        """创建并预热 Runtime"""
        # 这里需要获取 AgentConfig，简化处理
        from packages.agent.models.agent import AgentConfig

        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            # 创建默认配置
            raise ValueError(f"Agent not found: {agent_id}")

        if self._runtime_service:
            runtime = await self._runtime_service.create_runtime(
                agent=agent,
                workspace=workspace,
            )

            # 预热 (启动沙箱)
            await self._runtime_service.start_runtime(runtime.id)

            # 标记为已预热
            self._runtime_info[runtime.id] = {
                "warmed": True,
                "created_at": datetime.utcnow().isoformat(),
            }

            return runtime

        raise RuntimeError("RuntimeService not initialized")

    async def _get_runtime(self, runtime_id: str) -> Optional[AgentRuntime]:
        """获取 Runtime"""
        if self._runtime_service:
            return await self._runtime_service.get_runtime(runtime_id)
        return None

    async def _preheat_runtimes(self, count: int) -> None:
        """预热指定数量的 Runtime"""
        # 简化实现：实际需要有默认的 Agent 和 Workspace
        logger.info(f"Preheating {count} runtimes")

    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _health_check(self) -> None:
        """执行健康检查"""
        # 检查池中的 Runtime 状态
        for runtime_id in list(self._pool):
            runtime = await self._get_runtime(runtime_id)
            if not runtime or runtime.status == "failed":
                # 移除失败的 Runtime
                if runtime_id in self._pool:
                    self._pool.remove(runtime_id)
                logger.warning(f"Removed failed runtime: {runtime_id}")

    async def _auto_scale_loop(self) -> None:
        """自动扩缩容循环"""
        while True:
            try:
                await asyncio.sleep(10)  # 每 10 秒检查一次
                await self._auto_scale()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto scale error: {e}")

    async def _auto_scale(self) -> None:
        """自动扩缩容"""
        current_size = len(self._pool) + len(self._in_use)
        available = len(self._pool)

        # 如果池太小，扩容
        if available < self.config.min_size and current_size < self.config.max_size:
            # 需要预热更多
            pass  # TODO: 实现预热逻辑

        # 如果池太大且空闲，缩容
        if current_size > self.config.max_size:
            # 回收空闲的 Runtime
            pass  # TODO: 实现回收逻辑


# 全局单例
_preheat_pool: Optional[RuntimePreheatPool] = None


async def get_preheat_pool(db: AsyncSession) -> RuntimePreheatPool:
    """获取预热池单例"""
    global _preheat_pool
    if _preheat_pool is None:
        _preheat_pool = RuntimePreheatPool(db)
        await _preheat_pool.initialize()
    return _preheat_pool


async def close_preheat_pool() -> None:
    """关闭预热池"""
    global _preheat_pool
    if _preheat_pool:
        await _preheat_pool.shutdown()
        _preheat_pool = None
