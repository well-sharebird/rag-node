"""
Hooks 适配器：将旧 Hooks 系统适配到中间件接口（向后兼容）

迁移策略：
1. 保留 HookRegistry 作为兼容层
2. 创建 HooksAdapterMiddleware 包装旧 Hooks
3. 新代码使用中间件，旧代码继续用 Hooks
4. 最终完全迁移到中间件
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage

from .middleware import AgentMiddleware, RuntimeContext
from .state import AgentState

logger = logging.getLogger(__name__)


class HooksAdapterMiddleware(AgentMiddleware):
    """
    将旧 Hooks 系统适配到中间件接口
    
    映射关系：
    - pre_step hook → before_agent
    - post_step hook → after_agent
    - waterfall → wrap_tool_call
    """
    
    def __init__(self, hook_registry: Any):
        """
        初始化适配器
        
        Args:
            hook_registry: HookRegistry 实例
        """
        self.hooks = hook_registry
    
    async def before_agent(
        self,
        state: AgentState,
        runtime: RuntimeContext,
    ) -> AgentState:
        """
        映射 pre_step hook → before_agent
        
        核心逻辑：
        1. 构建 Step 对象（兼容旧接口）
        2. 执行所有 pre_step hooks
        3. 处理 AbortStep 异常
        4. 应用改写后的输入
        """
        # 快速路径：没有 hooks
        if not hasattr(self.hooks, 'pre_step') or not self.hooks.pre_step:
            return state
        
        # 动态导入（避免循环依赖）
        from packages.agent.execution.steps import Step, StepType, StepStatus
        from packages.agent.execution.hooks import ExecutionContext, HookResult, AbortStep
        
        # 构建 Step 对象
        step = Step(
            step_id=f"agent_{runtime.thread_id}",
            type=StepType.MODEL,
            name="orchestrator",
            input={"state": state, "thread_id": runtime.thread_id},
            status=StepStatus.PENDING,
        )
        
        # 构建执行上下文
        exec_ctx = ExecutionContext(
            session_id=runtime.thread_id,
            user_id=runtime.user_id,
        )
        
        # 执行所有 pre-step hooks
        for hook in self.hooks.pre_step:
            try:
                result: Optional[HookResult] = await hook(exec_ctx, step)
                
                # Hook 返回 None：无操作
                if result is None:
                    continue
                
                # Hook 拒绝执行
                if result.aborted:
                    logger.warning("[HooksAdapter] Step aborted by pre-hook: %s", result.reason)
                    state["_force_end"] = True
                    state["_end_reason"] = result.reason or "blocked by pre-step hook"
                    break
                
                # 应用改写后的输入
                if result.input is not None:
                    state = result.input.get("state", state)
                    logger.debug("[HooksAdapter] Input modified by pre-hook")
                
            except AbortStep as e:
                # Hook 抛出 AbortStep：中止执行
                logger.warning("[HooksAdapter] Step aborted by hook exception: %s", e.reason)
                state["_force_end"] = True
                state["_end_reason"] = e.reason
                break
                
            except Exception as e:
                # Hook 异常：记录日志，继续执行
                logger.error("[HooksAdapter] Pre-hook error: %s", e, exc_info=True)
                # 继续执行下一个 hook
        
        return state
    
    async def after_agent(
        self,
        state: AgentState,
        runtime: RuntimeContext,
        response: AIMessage = None,
    ) -> AgentState:
        """
        映射 post_step hook → after_agent
        
        核心逻辑：
        1. 构建 Step 对象（包含输出）
        2. 执行所有 post_step hooks
        3. 应用改写后的输出
        """
        # 快速路径：没有 hooks
        if not hasattr(self.hooks, 'post_step') or not self.hooks.post_step:
            return state
        
        # 动态导入
        from packages.agent.execution.steps import Step, StepType, StepStatus
        from packages.agent.execution.hooks import ExecutionContext
        
        # 构建 Step 对象（包含输出）
        step = Step(
            step_id=f"agent_{runtime.thread_id}",
            type=StepType.MODEL,
            name="orchestrator",
            input={"state": state, "thread_id": runtime.thread_id},
            output={"response": response, "state": state},
            status=StepStatus.COMPLETED,
        )
        
        # 构建执行上下文
        exec_ctx = ExecutionContext(
            session_id=runtime.thread_id,
            user_id=runtime.user_id,
        )
        
        # 执行所有 post-step hooks
        for hook in self.hooks.post_step:
            try:
                result: Optional[HookResult] = await hook(exec_ctx, step)
                
                # Hook 返回 None：无操作
                if result is None:
                    continue
                
                # 应用改写后的输出
                if result.output is not None:
                    state = result.output.get("state", state)
                    logger.debug("[HooksAdapter] Output modified by post-hook")
                
            except Exception as e:
                # Hook 异常：记录日志，继续执行
                logger.error("[HooksAdapter] Post-hook error: %s", e, exc_info=True)
                # 继续执行下一个 hook
        
        return state
    
    async def wrap_tool_call(
        self,
        ctx: RuntimeContext,
        tool_call: Dict[str, Any],
        tool_fn: Callable[..., Awaitable[Any]],
    ) -> Any:
        """
        映射 waterfall → wrap_tool_call
        
        核心逻辑：
        1. 执行 waterfall transforms（tools/pre-execute）
        2. 调用原始工具函数
        3. 返回结果
        """
        # 快速路径：没有 waterfalls
        if not hasattr(self.hooks, 'waterfalls') or not self.hooks.waterfalls:
            return await tool_fn(tool_call)
        
        # 获取 waterfall handlers
        handlers = self.hooks.waterfalls.get("tools/pre-execute", [])
        if not handlers:
            return await tool_fn(tool_call)
        
        # 执行 waterfall：逐层改写 payload
        payload = tool_call
        for handler in handlers:
            try:
                payload = await _invoke(handler, payload)
            except Exception as e:
                logger.warning("[HooksAdapter] Waterfall error: %s", e)
                # 继续执行下一个 handler
        
        # 调用工具函数
        return await tool_fn(payload)


async def _invoke(fn: Callable, *args, **kwargs) -> Any:
    """
    调用函数（支持同步/异步）
    
    兼容旧 Hooks 系统的 _invoke 实现
    """
    import asyncio
    
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result
