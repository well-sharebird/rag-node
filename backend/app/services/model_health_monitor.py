"""
模型健康状态定时检测服务

定期检测所有启用模型的健康状态，自动更新 active/error 状态。
采用 asyncio 后台任务实现，集成到 FastAPI lifespan 生命周期。
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.model_config import ModelConfig
from app.services.model_service import test_model_connection

logger = logging.getLogger("app.services.model_health_monitor")


class ModelHealthMonitor:
    """模型健康状态定时检测器"""

    def __init__(
        self,
        check_interval_seconds: int = 300,  # 默认 5 分钟
        check_timeout_ms: int = 10000,       # 每个模型测试超时 10 秒
        max_concurrent_checks: int = 5,      # 并发检测数
    ):
        self.check_interval = check_interval_seconds
        self.check_timeout_ms = check_timeout_ms
        self.max_concurrent = max_concurrent_checks
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "last_run_at": None,
        }

    async def start(self, db_session_factory):
        """启动定时检测任务"""
        self._running = True
        self._task = asyncio.create_task(
            self._run_monitor_loop(db_session_factory)
        )
        logger.info(
            "Model health monitor started | interval=%ds timeout=%dms max_concurrent=%d",
            self.check_interval, self.check_timeout_ms, self.max_concurrent
        )

    async def stop(self):
        """停止定时检测任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            "Model health monitor stopped | stats=%s",
            self._stats
        )

    def get_stats(self) -> dict:
        """获取监控统计信息"""
        return self._stats.copy()

    async def _run_monitor_loop(self, db_session_factory):
        """主检测循环"""
        from app.core.database import async_session_factory

        while self._running:
            try:
                async with async_session_factory() as session:
                    await self._check_all_models(session)
                    self._stats["last_run_at"] = datetime.utcnow().isoformat()
            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error("Monitor loop error: %s", e)

            # 等待下次检测
            await asyncio.sleep(self.check_interval)

    async def _check_all_models(self, session: AsyncSession):
        """检测所有启用的模型"""
        # 只检测启用的模型
        result = await session.execute(
            select(ModelConfig).where(ModelConfig.is_enabled == True)
        )
        models = result.scalars().all()

        if not models:
            logger.debug("No enabled models to check")
            return

        self._stats["total_checks"] += len(models)
        logger.info("Checking %d enabled models", len(models))

        # 并发控制
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def check_with_semaphore(model):
            async with semaphore:
                await self._check_single_model(session, model)

        tasks = [check_with_semaphore(model) for model in models]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_single_model(
        self,
        session: AsyncSession,
        model: ModelConfig
    ):
        """检测单个模型"""
        import time
        start = time.time()

        try:
            result = await test_model_connection(
                session,
                model.id,
                test_input=None  # 使用默认测试输入
            )

            if result.get("success"):
                self._stats["successful_checks"] += 1
                logger.debug(
                    "Model healthy | id=%d name=%s latency=%dms",
                    model.id, model.name, result.get("latency_ms")
                )
            else:
                self._stats["failed_checks"] += 1
                logger.warning(
                    "Model check failed | id=%d name=%s error=%s",
                    model.id, model.name, result.get("message")
                )

        except asyncio.TimeoutError:
            self._stats["failed_checks"] += 1
            logger.warning(
                "Model check timeout | id=%d name=%s timeout=%dms",
                model.id, model.name, self.check_timeout_ms
            )
        except Exception as e:
            self._stats["failed_checks"] += 1
            logger.error(
                "Model check error | id=%d name=%s error=%s",
                model.id, model.name, str(e)
            )


# 全局单例
_monitor: Optional[ModelHealthMonitor] = None


def get_monitor() -> Optional[ModelHealthMonitor]:
    """获取全局监控实例"""
    return _monitor


async def start_monitor(
    db_session_factory=None,
    check_interval_seconds: int = 300,
    check_timeout_ms: int = 10000,
    max_concurrent_checks: int = 5,
) -> ModelHealthMonitor:
    """启动监控服务"""
    global _monitor
    _monitor = ModelHealthMonitor(
        check_interval_seconds=check_interval_seconds,
        check_timeout_ms=check_timeout_ms,
        max_concurrent_checks=max_concurrent_checks,
    )
    await _monitor.start(db_session_factory)
    return _monitor


async def stop_monitor():
    """停止监控服务"""
    global _monitor
    if _monitor:
        await _monitor.stop()
        _monitor = None
