"""Step 执行门面：集成 StepDrivenEngine，提供结构化事件流（P0/P1 集成）。

StepExecutionRuntime 现在内部使用 StepDrivenEngine 执行，而非直接包装 run_stream。
保留原有事件协议，确保 API 层零改动。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from packages.agent.execution.events import ExecutionEvent, ExecutionEventStream, ExecutionEventType
from packages.agent.execution.hooks import AbortStep, HookRegistry
from packages.agent.execution.lifecycle import AgentState, AgentStatus
from packages.agent.execution.sourcing import (
    EventSourcedState,
    ExecutionCheckpoint,
    MemoryStore,
    SessionLog,
)
from packages.agent.execution.steps import (
    ExecutionContext,
    Step,
    StepStatus,
    StepType,
    Turn,
    TurnStatus,
)
from packages.agent.execution.step_engine import StepDrivenEngineV2

logger = logging.getLogger(__name__)


class StepExecutionRuntime:
    """Step 执行门面。内部委托给 StepDrivenEngine 执行。
    
    Deprecated: Phase 1 重构后已废弃，请使用 StepExecutor 替代。
    """
    
    def __init__(self, orchestrator: Any, *, session_id: Optional[str] = None,
                 user_id: Optional[int] = None, agent_id: Optional[str] = None):
        self._orchestrator = orchestrator
        warnings.warn(
            "StepExecutionRuntime is deprecated and will be removed in a future version. "
            "Please use StepExecutor instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.session_id = session_id
        self.user_id = user_id
        self.agent_id = agent_id
        # 子系统
        self.hooks = HookRegistry()
        self.store = MemoryStore()
        self.session_log = SessionLog(self.store)
        self.checkpoint = ExecutionCheckpoint(self.store)
        self._events = ExecutionEventStream()
        # 状态
        self.turn: Optional[Turn] = None
        self.ctx: Optional[ExecutionContext] = None
        self.agent = AgentState(agent_id or "default")
        self.state = EventSourcedState(self.session_log)

    def send(self, content: str) -> None:
        """向当前执行中的 turn 追加指令（可在 step 间被消费/注入）。"""
        self.agent.send({"type": "inject", "content": content, "by": "user"})
        if self.turn and self.turn.steps:
            self.turn.steps[-1].add_injection(content)

    @property
    def event_stream(self) -> ExecutionEventStream:
        return self._events

    def drain(self) -> Optional[ExecutionEvent]:
        return self._events.try_get()

    def get_plan(self) -> Optional[Dict[str, Any]]:
        """获取当前执行计划。"""
        return self.ctx.plan if self.ctx else None

    async def execute_stream(self, query: str, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """使用 StepDrivenEngine 执行，产出结构化事件流。"""
        self.turn = Turn.new(query, user_id=self.user_id, session_id=self.session_id,
                             agent_id=self.agent_id)
        self.ctx = ExecutionContext(self.turn)
        self.ctx.user_id = self.user_id
        self.ctx.session_id = self.session_id
        self.ctx.agent_id = self.agent_id

        turn_id = self.turn.turn_id
        turn_no = 1
        self.turn.start()
        self.agent.begin_turn()

        # turn/start 事件 + 日志
        self._events.publish(ExecutionEventType.TURN_START, turn_id=turn_id, data={"query": query})
        await self.session_log.append(self.session_id, "turn/start", {"query": query}, turn=turn_no)
        await self.session_log.append(self.session_id, "user/message", {"content": query}, turn=turn_no)

        try:
            # 方案 B：使用 StepDrivenEngine v2（图驱动）
            # 获取 LLM 和 tools
            llm = await self._orchestrator._create_llm()
            tools = self._orchestrator._load_sub_tools(
                kwargs.get('main_agent_cfg', None).tools_whitelist 
                if kwargs.get('main_agent_cfg') 
                else ["save_workspace_file"]
            )
            
            # 创建 StepDrivenEngine v2（图驱动包装器）
            engine = StepDrivenEngineV2(
                orchestrator=self._orchestrator,
                llm=llm,
                tools=tools,
                hooks=self.hooks,
                session_log=self.session_log,
                checkpoint=self.checkpoint,
                session_id=self.session_id,
                user_id=self.user_id,
            )
            
            # 图驱动执行
            history = kwargs.get('history', [])
            async for ev in engine.execute(query, history=history):
                yield ev
        finally:
            # 结束 turn
            self.turn.complete()
            self.agent.end_turn()
            self._events.publish(ExecutionEventType.TURN_END, turn_id=turn_id,
                                 data={"status": self.turn.status.value,
                                       "duration_ms": self.turn.duration_ms})
            await self.session_log.append(
                self.session_id, "turn/end",
                {"status": self.turn.status.value, "duration_ms": self.turn.duration_ms},
                turn=turn_no)


# ============================================================================
# 别名类（Phase 1 重构：渐进式重命名）
# ============================================================================

# ============================================================================
# 别名类（已移除）
# ============================================================================
# StepExecutor 和 StepExecutionRuntime 已在 Phase 4 移除
# 新代码请直接使用 StepDrivenEngineV2
# ============================================================================
