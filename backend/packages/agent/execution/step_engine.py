"""StepDrivenEngine - 图驱动执行引擎

核心设计：
1. 使用 RuntimeEngine 作为执行引擎
2. 纯 Agent Loop 图（think→act→think）
3. 保留横切关注点（Hooks/Checkpoints/事件流）

架构:
```
StepDrivenEngine (包装器 - 横切关注点)
    ↓
RuntimeEngine (运行时引擎)
    ↓
MiddlewareChain (中间件链)
    ↓
Agent Graph (纯 Agent Loop)
```
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from packages.agent.runtime import make_agent, RuntimeEngine
from packages.agent.execution.hooks import HookRegistry
from packages.agent.execution.sourcing import ExecutionCheckpoint, SessionLog

logger = logging.getLogger(__name__)


class StepDrivenEngine:
    """Step 驱动引擎（图驱动包装器）。
    
    核心设计：
    1. 使用 RuntimeEngine 作为执行引擎
    2. 纯 Agent Loop 图（think→act→think）
    3. 保留横切关注点（Hooks/Checkpoints/事件流）
    
    职责:
    - Hooks 执行（Pre/Post）
    - Checkpoints 管理
    - 事件流广播
    - 用户查询转 AgentState
    """

    def __init__(
        self,
        llm: Any,
        tools: List[Any],
        *,
        hooks: Optional[HookRegistry] = None,
        session_log: Optional[SessionLog] = None,
        checkpoint: Optional[ExecutionCheckpoint] = None,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        max_iterations: int = 10,
        permission_engine: Optional[Any] = None,
        system_prompt: Optional[str] = None,
    ):
        """
        初始化 StepDrivenEngine
        
        Args:
            llm: LLM 实例
            tools: 工具列表
            hooks: Hook 注册表（可选）
            session_log: 会话日志（可选）
            checkpoint: 检查点管理器（可选）
            session_id: 会话 ID（可选）
            user_id: 用户 ID（可选）
            max_iterations: 最大迭代次数
            permission_engine: 权限引擎（可选）
            system_prompt: 系统提示词（可选）
        """
        self._llm = llm
        self._tools = tools
        self._hooks = hooks
        self._session_log = session_log
        self._checkpoint = checkpoint
        self._session_id = session_id
        self._user_id = user_id
        self._max_iterations = max_iterations
        self._permission_engine = permission_engine
        self._system_prompt = system_prompt
        
        # 创建运行时引擎
        self._engine = self._create_engine()

    @property
    def hooks(self) -> Optional[HookRegistry]:
        """暴露 hooks 属性（供 ExecutionOrchestrator 访问）"""
        return self._hooks

    def _create_engine(self) -> RuntimeEngine:
        """创建运行时引擎"""
        return make_agent(
            llm=self._llm,
            tools=self._tools,
            hook_registry=self._hooks,
            max_iterations=self._max_iterations,
            permission_engine=self._permission_engine,
            system_prompt=self._system_prompt,
        )

    async def execute(
        self,
        query: str,
        *,
        history: Optional[List[Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行一次任务（委托给 RuntimeEngine）
        
        Args:
            query: 用户查询
            history: 历史消息列表（可选）
            
        Yields:
            Dict[str, Any]: 执行事件
        """
        # 1. 检查点恢复
        if self._checkpoint and self._checkpoint.has_checkpoint():
            logger.info("[StepDrivenEngine] Restoring from checkpoint")
            try:
                checkpoint_data = await self._checkpoint.restore()
                logger.info("[StepDrivenEngine] Restored from checkpoint")
            except Exception as e:
                logger.error("[StepDrivenEngine] Failed to restore from checkpoint: %s", e)
        
        # 2. 执行
        thread_id = self._session_id or f"anon_{asyncio.get_event_loop().time()}"
        user_id = self._user_id or 0
        
        try:
            # 使用 RuntimeEngine 执行
            async for event in self._engine.execute(
                query=query,
                thread_id=thread_id,
                user_id=user_id,
                session_id=self._session_id,
                history=history,
            ):
                # 会话日志记录
                if self._session_log:
                    await self._session_log.append(
                        self._session_id or "anon",
                        "step/event",
                        {"event": event},
                    )
                
                yield event
                
        except Exception as e:
            # 检查是否是审批中断
            from langgraph.errors import GraphInterrupt
            if isinstance(e, GraphInterrupt):
                logger.info("[StepDrivenEngine] GraphInterrupt 捕获，提取审批请求")
                raise
            else:
                logger.error("[StepDrivenEngine] Execution error: %s", e, exc_info=True)
                raise
        
        # 3. 保存检查点
        if self._checkpoint:
            try:
                await self._checkpoint.save({"thread_id": thread_id})
                logger.info("[StepDrivenEngine] Checkpoint saved")
            except Exception as e:
                logger.error("[StepDrivenEngine] Failed to save checkpoint: %s", e)
