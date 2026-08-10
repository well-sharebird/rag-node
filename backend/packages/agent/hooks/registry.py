"""Hook 注册器 - 统一中间件注册机制"""
from typing import Callable, Any
from enum import Enum
from collections import defaultdict
import logging
import asyncio

logger = logging.getLogger(__name__)


class HookPoint(str, Enum):
    """Hook 挂载点 — 对应 Agent Loop 的关键阶段"""
    BEFORE_AGENT = "before_agent"        # 执行前
    AFTER_AGENT = "after_agent"          # 执行后
    BEFORE_THINK = "before_think"        # LLM 推理前
    AFTER_THINK = "after_think"          # LLM 推理后
    BEFORE_ACT = "before_act"            # 工具执行前
    AFTER_ACT = "after_act"              # 工具执行后
    BEFORE_OUTPUT = "before_output"      # 输出治理前
    AFTER_OUTPUT = "after_output"        # 输出治理后


class HookRegistry:
    """Hook 注册与执行器"""

    def __init__(self):
        self._hooks: dict[HookPoint, list[tuple[int, Callable]]] = defaultdict(list)

    def register(self, point: HookPoint, handler: Callable, priority: int = 0):
        """注册 Hook

        Args:
            point: 挂载点
            handler: async (state: dict) -> dict | None
            priority: 优先级（数字越小越先执行）
        """
        self._hooks[point].append((priority, handler))
        # 按优先级排序
        self._hooks[point].sort(key=lambda x: x[0])
        logger.info(f"Hook registered: {point.value} -> {handler.__name__}")

    async def run(self, point: HookPoint, state: dict) -> dict:
        """执行某个挂载点的所有 Hook"""
        for _, handler in self._hooks.get(point, []):
            try:
                result = await handler(state) if asyncio.iscoroutinefunction(handler) else handler(state)
                if result:
                    state.update(result)
            except Exception as e:
                logger.error(f"Hook {handler.__name__} at {point.value} failed: {e}")
                # Hook 失败不中断主流程
        return state

    def has_hooks(self, point: HookPoint) -> bool:
        return bool(self._hooks.get(point))


# 全局单例
_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    return _registry


def hook(point: HookPoint, priority: int = 0):
    """装饰器：注册 Hook"""
    def decorator(func):
        _registry.register(point, func, priority)
        return func
    return decorator
