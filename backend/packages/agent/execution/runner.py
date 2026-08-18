"""Step 执行门面：包装 OrchestratorRuntime.run_stream，产出结构化事件流（P0/P1 集成）。

不重写 OrchestratorRuntime 的业务逻辑，而是在其外层：
1. 把一次 run_stream 建模为一个 **Turn**，并在关键节点产出 step 事件（plan/direct/dispatch/aggregate）。
2. 在 plan/step 边界执行 **hooks**（pre/post-step、waterfall）。
3. 把结构化事件追加进 **SessionLog**（事件溯源）。
4. 暴露 **agent.send** 追加指令与动态调整 plan（P0-2/3）。

/execute/stream 可拿到的结构化事件（在原有扁平事件之外）：
    turn/start, plan/created, step/start, step/end, turn/end ...
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

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

logger = logging.getLogger(__name__)


class StepExecutionRuntime:
    """Step 执行门面（装饰器）。包装 run_stream，注入结构化执行能力。"""

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
        self.sourcing_state = EventSourcedState(self.session_log)
        self.checkpoint = ExecutionCheckpoint(self.store)
        self.agent = AgentState(agent_id or "main")
        self.turn: Optional[Turn] = None
        self.ctx: Optional[ExecutionContext] = None
        self._events = ExecutionEventStream()

    # ---------------- plan 动态调整（P0-3） ----------------
    def get_plan(self) -> Optional[Dict[str, Any]]:
        return self.ctx.plan if self.ctx else None

    def update_plan(self, plan: Dict[str, Any]) -> None:
        """执行中动态调整 plan（如失败重试、边界修正）。"""
        if self.ctx is None:
            raise RuntimeError("Execution not started")
        self.ctx.plan = plan
        self.ctx.vars["plan_revision"] = self.ctx.vars.get("plan_revision", 0) + 1
        self._events.publish(
            ExecutionEventType.PLAN_UPDATED, turn_id=self.turn.turn_id,
            data={"plan": plan, "revision": self.ctx.vars["plan_revision"]})
        logger.info("[StepRuntime] plan 更新 rev=%s", self.ctx.vars["plan_revision"])

    # ---------------- agent.send 追加指令（P0-2） ----------------
    def send(self, content: str) -> None:
        """向当前执行中的 turn 追加指令（可在 step 间被消费/注入）。"""
        self.agent.send({"type": "inject", "content": content, "by": "user"})
        if self.turn and self.turn.steps:
            self.turn.steps[-1].add_injection(content)

    # ---------------- 事件流获取 ----------------
    @property
    def event_stream(self) -> ExecutionEventStream:
        return self._events

    def drain(self) -> Optional[ExecutionEvent]:
        return self._events.try_get()

    # ---------------- 主入口 ----------------
    async def execute_stream(self, query: str, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """等价 OrchestratorRuntime.run_stream，但外层包了 Turn/Step 结构化事件与钩子。"""
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
            async for ev in self._run_wrapped(query, turn_no, turn_id, kwargs):
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

    async def _run_wrapped(self, query: str, turn_no: int, turn_id: str,
                           kwargs: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """逐事件包装：识别 plan / sub_agent / token，映射为 step 事件，并跑钩子。"""
        # 预注册一个 plan step（plan 是 turn 的第一个执行动作）
        plan_step = self.ctx.register(Step.new(StepType.PLAN, name="plan", parent_id=None))
        self._events.publish(ExecutionEventType.STEP_START, turn_id=turn_id,
                             step_id=plan_step.step_id, data=plan_step.to_dict())
        pre = await self.hooks.run_pre_step(self.ctx, plan_step)
        if pre.aborted:
            plan_step.skip(pre.reason)
            self._events.publish(ExecutionEventType.STEP_END, turn_id=turn_id,
                                 step_id=plan_step.step_id, data=plan_step.to_dict())
            return

        # 兜底：把 run_stream 事件类型→结构化事件增量广播
        token_buf: list = []
        step: Optional[Step] = None

        async for raw in self._orchestrator.run_stream(query, **kwargs):
            etype = raw.get("type") if isinstance(raw, dict) else None
            data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else {}

            # plan 事件 → 记录 plan + 结束 plan step + 各派发 step
            if etype == "orchestrator_plan":
                plan_step.complete({"plan": data})
                self.ctx.plan = data
                self._events.publish(ExecutionEventType.PLAN_CREATED, turn_id=turn_id,
                                     step_id=plan_step.step_id, data=data)
                await self.session_log.append(
                    self.session_id, "plan/created", {"plan": data}, turn=turn_no)
                self._events.publish(ExecutionEventType.STEP_END, turn_id=turn_id,
                                     step_id=plan_step.step_id, data=plan_step.to_dict())
                # pre-step hook 对 plan 的改写机会
                data = await self.hooks.run_waterfall("plan/created", data)
                if data:
                    self.ctx.plan = data
                step = None
                yield raw
                continue

            # sub_agent running → 开启一个 dispatch/sub_agent step
            if etype == "sub_agent" and data.get("status") == "running":
                step = self.ctx.register(Step.new(
                    StepType.DISPATCH, name=f"dispatch:{data.get('sub_agent_id','sub')}",
                    parent_id=None))
                step.input = data
                step.start()
                self._events.publish(ExecutionEventType.SUB_AGENT_START, turn_id=turn_id,
                                     step_id=step.step_id, data=data)
                self._events.publish(ExecutionEventType.STEP_START, turn_id=turn_id,
                                     step_id=step.step_id, data=data)
                yield raw
                continue

            # sub_agent done → 完成上一个 step
            if etype == "sub_agent" and data.get("status") == "done":
                if step is not None:
                    step.complete({"sub_agent_id": data.get("sub_agent_id"),
                                   "success": data.get("success"),
                                   "content": (data.get("content") or "")[:200]})
                    self._events.publish(ExecutionEventType.SUB_AGENT_END, turn_id=turn_id,
                                         step_id=step.step_id, data=data)
                    self._events.publish(ExecutionEventType.STEP_END, turn_id=turn_id,
                                         step_id=step.step_id, data=step.to_dict())
                    post = await self.hooks.run_post_step(self.ctx, step)
                    await self.session_log.append(
                        self.session_id, "sub_agent/done",
                        {"sub_agent_id": data.get("sub_agent_id"), "success": data.get("success")},
                        turn=turn_no, step=len(self.turn.steps))
                step = None
                yield raw
                continue

            # 聚合/直答 token → 收集
            if etype == "token":
                content = (data.get("content") or raw.get("content") or "") if isinstance(raw, dict) else ""
                token_buf.append(content)
                await self.session_log.append(
                    self.session_id, "assistant/message",
                    {"content": content}, turn=turn_no, step=len(self.turn.steps))
                self._events.publish(ExecutionEventType.LLM_STREAM, turn_id=turn_id,
                                     step_id=(step.step_id if step else plan_step.step_id),
                                     data={"content": content})
                yield raw
                continue

            # tool_event 透传 + 事件化
            if etype == "tool_event":
                self._events.publish(ExecutionEventType.TOOL_START
                                     if data.get("phase") == "start" else ExecutionEventType.TOOL_END,
                                     turn_id=turn_id, data=data)
                yield raw
                continue

            yield raw

        # 聚合 step 收尾：把 token 归入 aggregate step
        if step is None:
            agg = self.ctx.register(Step.new(StepType.AGGREGATE, name="aggregate", parent_id=None))
            agg.start()
            agg.complete({"content": "".join(token_buf)[:200]})
            self._events.publish(ExecutionEventType.STEP_END, turn_id=turn_id,
                                 step_id=agg.step_id, data=agg.to_dict())

        if plan_step.status == StepStatus.PENDING:
            plan_step.complete({"direct_only": True})

        # 检查点
        await self.checkpoint.save(
            self.session_id or "anon", turn_id,
            {"status": "done", "steps": len(self.turn.steps)},
            {"plan": self.ctx.plan, "final": "".join(token_buf)[:200]})
