"""钩子系统：Pre/Post-Step Hook 与 waterfall 拦截器（P1）。

参考 DeepSeek Harness：
- **pre-step hook**：step 执行前调用，可改写输入或拒绝（抛 AbortStep）。
- **post-step hook**：step 执行后调用，可改写输出（脱敏、质检）。
- **waterfall**：在 agent/request、llm/stream、tools/pre-execute 等节点间插桩，逐层改写 payload。

复用现有 PluginRegistry 的 emit（通知）/ waterfall（中间件）机制，提供更高层的
StepHook 抽象与执行时调度。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from packages.agent.execution.steps import ExecutionContext, Step, StepStatus

logger = logging.getLogger(__name__)


class AbortStep(Exception):
    """pre-step 钩子拒绝执行当前 step。"""
    def __init__(self, reason: str, step_id: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.step_id = step_id


@dataclass
class HookResult:
    """钩子处理结果。"""
    input: Optional[Dict[str, Any]] = None     # 可能被改写后的输入
    output: Optional[Dict[str, Any]] = None    # post-step 改写后的输出
    aborted: bool = False
    reason: str = ""


# 钩子签名：async def hook(ctx, step) -> Optional[HookResult]
Hook = Callable[[ExecutionContext, Step], Awaitable[Optional[HookResult]]]


@dataclass
class HookRegistry:
    """插件化钩子注册表（动态插拔，P1-5/6/8）。"""
    pre_step: List[Hook] = field(default_factory=list)
    post_step: List[Hook] = field(default_factory=list)
    # waterfall：event 名 → [transform(payload) -> payload]
    waterfalls: Dict[str, List[Callable[[Any], Any]]] = field(default_factory=dict)

    def add_pre_step(self, hook: Hook, name: str = "") -> None:
        self.pre_step.append(hook)
        _attach_name(hook, name, "pre_step")

    def add_post_step(self, hook: Hook, name: str = "") -> None:
        self.post_step.append(hook)
        _attach_name(hook, name, "post_step")

    def add_waterfall(self, event: str, transform: Callable[[Any], Any], name: str = "") -> None:
        self.waterfalls.setdefault(event, []).append(transform)

    def remove(self, hook) -> None:
        if hook in self.pre_step:
            self.pre_step.remove(hook)
        if hook in self.post_step:
            self.post_step.remove(hook)
        for event in list(self.waterfalls):
            if hook in self.waterfalls[event]:
                self.waterfalls[event].remove(hook)

    async def run_pre_step(self, ctx: ExecutionContext, step: Step) -> HookResult:
        """执行全部 pre-step 钩子。任一返回 aborted 即中止。"""
        result = HookResult(input=step.input or {})
        for hook in self.pre_step:
            try:
                r = await hook(ctx, step)
                if r is None:
                    continue
                if r.aborted:
                    result.aborted = True
                    result.reason = r.reason or "blocked by pre-step hook"
                    step.skip(result.reason)
                    break
                if r.input is not None:
                    result.input = r.input
                    step.input = r.input
            except AbortStep as e:
                result.aborted = True
                result.reason = e.reason
                step.skip(e.reason)
                break
            except Exception as e:
                logger.warning("[Hook] pre_step 异常被吞并继续: %s", e)
        return result

    async def run_post_step(self, ctx: ExecutionContext, step: Step) -> HookResult:
        """执行全部 post-step 钩子，可改写 step.output。"""
        result = HookResult(output=step.output)
        for hook in self.post_step:
            try:
                r = await hook(ctx, step)
                if r is not None and r.output is not None:
                    result.output = r.output
                    step.output = r.output
            except Exception as e:
                logger.warning("[Hook] post_step 异常被吞并继续: %s", e)
        return result

    async def run_waterfall(self, event: str, payload: Any) -> Any:
        """执行 waterfall：逐层改写 payload 并传给下一个。"""
        handlers = self.waterfalls.get(event, [])
        result = payload
        for handler in handlers:
            try:
                result = await _invoke(handler, result)
            except Exception as e:
                logger.warning("[Hook] waterfall %s 异常: %s", event, e)
        return result


async def _invoke(fn: Callable, *args, **kwargs):
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result


def _attach_name(hook, name: str, kind: str) -> None:
    if name:
        setattr(hook, "__hook_name__", f"{kind}:{name}")
    elif not hasattr(hook, "__hook_name__"):
        setattr(hook, "__hook_name__", getattr(hook, "__name__", kind))
