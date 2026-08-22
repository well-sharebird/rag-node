"""MiddlewareChain - 中间件执行链

在自定义 TAO 图节点中按生命周期驱动一组 AgentMiddleware。
向下兼容异步中间件方法（abefore_* / aafter_* 优先），合并返回的 State 更新。
"""
import inspect
import logging
from typing import Any, List, Optional

from .types import AgentMiddleware, Runtime

logger = logging.getLogger(__name__)


class MiddlewareChain:
    """持有并调度一组 AgentMiddleware，提供 agent/model 生命周期钩子。"""

    def __init__(self, middlewares: Optional[List[AgentMiddleware]] = None):
        self.middlewares = list(middlewares or [])

    def __bool__(self) -> bool:
        return bool(self.middlewares)

    @staticmethod
    def _runtime() -> Runtime:
        return Runtime()

    async def _apply(self, state: dict, prefix: str) -> dict:
        """调用所有中间件的 <prefix>_agent / <prefix>_model 方法并合并 state。"""
        rt = self._runtime()
        for mw in self.middlewares:
            for method_name in (f"a{prefix}", f"{prefix}"):
                fn = getattr(mw, method_name, None)
                if fn is None:
                    continue
                if fn is getattr(AgentMiddleware, method_name, object()):
                    continue  # 基类默认实现，跳过
                try:
                    result = await fn(state, rt) if inspect.iscoroutinefunction(fn) else fn(state, rt)
                    if isinstance(result, dict):
                        state.update(result)
                except Exception as e:
                    logger.warning("Middleware %s.%s 失败: %s", type(mw).__name__, method_name, e)
        return state

    async def before_agent(self, state: dict) -> dict:
        return await self._apply(state, "before_agent")

    async def after_agent(self, state: dict) -> dict:
        return await self._apply(state, "after_agent")

    async def before_model(self, state: dict) -> dict:
        return await self._apply(state, "before_model")

    async def after_model(self, state: dict) -> dict:
        return await self._apply(state, "after_model")
