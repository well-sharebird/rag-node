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
from packages.agent.execution.step_engine import StepDrivenEngine

logger = logging.getLogger(__name__)


class StepExecutionRuntime:
    """Step 执行门面。内部委托给 StepDrivenEngine 执行。"""

    def __init__(self, orchestrator: Any, *, session_id: Optional[str] = None,
                 user_id: Optional[int] = None, agent_id: Optional[str] = None):
        self._orchestrator = orchestrator
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
            # 创建 StepDrivenEngine 并执行
            engine = StepDrivenEngine(
                self._orchestrator,
                hooks=self.hooks,
                signals=type('obj', (object,), {
                    'checkpoint': self.checkpoint,
                    'session_log': self.session_log,
                    'session_id': self.session_id,
                    'agent': self.agent,
                    '_events': self._events,
                })(),
                session_id=self.session_id,
                user_id=self.user_id,
            )
            
            # 提取 run_stream 兼容的参数
            main_prompt = kwargs.get('main_prompt', '')
            main_agent_cfg = kwargs.get('main_agent_cfg')
            catalog = kwargs.get('catalog', [])
            run_mode = kwargs.get('run_mode', 'serial')
            allow_sub_agents = kwargs.get('allow_sub_agents', True)
            history = kwargs.get('history', [])
            
            async for ev in engine.execute(
                query, main_prompt or '', main_agent_cfg, catalog,
                run_mode=run_mode, allow_sub_agents=allow_sub_agents, history=history
            ):
                # Sync turn from engine
                if engine.turn:
                    self.turn = engine.turn
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
