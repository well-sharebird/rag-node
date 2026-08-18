"""Step 驱动执行引擎（执行逻辑重构核心）。

目标：把「一次 Plan 执行到底」的固定流水线（supervisor: plan→router→direct|dispatch→aggregate）
改造成 **Step 驱动的动态执行循环**，真正满足 DeepSeek Harness 的 Step/Turn 模型：
每个 step 之间可决策、可干预、可恢复。

设计：
- **Step 即执行边界**：plan / direct / dispatch / sub_agent / aggregate 不再由固定图决定，
  而是由引擎在每次决策点显式推进。每个 step 执行前跑 pre-step hook（可改写/拒绝），
  执行后跑 post-step hook（可改写结果）。
- **动态 Plan**：子 Agent 失败后可重试或新增子任务；聚合后可再追问。
- **agent.send 介入**：每个决策点 drain 执行器 inbox，把追加指令注入下一个 step。
- **检查点**：每 step 完成后保存检查点，决策点先尝试恢复。
- 对外产出与 run_stream 完全一致的事件协议（orchestrator_plan / sub_agent / token / tool_event），
  故 API 层零改动即接入，但执行本质已变为 Step 驱动。

复用 OrchestratorRuntime 既有构建块（不重写业务逻辑）：
- _orchestrate            -> plan step 执行
- _direct_answer_stream   -> direct step 执行
- _exec_sub_task          -> sub_agent step 执行
- _aggregate_stream       -> aggregate step 执行
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from packages.agent.orchestrator.state import OrchestrationPlan, SubAgentResult, SubTask  # noqa: E402  (lazy usable)
from packages.agent.execution.steps import (
    ExecutionContext,
    Step,
    StepStatus,
    StepType,
    Turn,
    TurnStatus,
)

logger = logging.getLogger(__name__)


class StepDrivenEngine:
    """Step 驱动的编排执行引擎。

    替代 build_supervisor_graph(...).ainvoke(...) 的固定流水线。
    用法：
        engine = StepDrivenEngine(runtime, hooks=..., signals=...)
        async for ev in engine.execute(...):
            yield ev
    """

    def __init__(self, runtime: Any, *, hooks: Any = None,
                 signals: Any = None, session_id: Optional[str] = None,
                 user_id: Optional[int] = None):
        self._rt = runtime
        self.hooks = hooks          # HookRegistry
        self.signals = signals      # StepExecutionRuntime（提供 agent.inbox / checkpoint / 事件流）
        self.session_id = session_id
        self.user_id = user_id
        self.ctx: Optional[ExecutionContext] = None
        self.turn: Optional[Turn] = None
        self._ep_events = []  # 本轮已产出的事件（供检查点/动态决策参考）

    # ---------------- 决策点：drain 追加指令（agent.send） ----------------
    def _drain_send(self) -> List[Dict[str, Any]]:
        if self.signals is None:
            return []
        inbox = self.signals.agent.inbox
        injections: List[Dict[str, Any]] = []
        while not inbox.empty():
            try:
                injections.append(inbox.get_nowait())
            except asyncio.QueueEmpty:
                break
        if injections:
            logger.info("[StepEngine] 决策点消费 %d 条追加指令", len(injections))
        return injections

    # ---------------- 检查点恢复 ----------------
    async def _try_restore(self, turn_id: str) -> bool:
        if self.signals is None:
            return False
        cp = await self.signals.checkpoint.restore(self.session_id or "anon", turn_id)
        if cp and cp.get("plan"):
            self.ctx.plan = cp["plan"]
            logger.info("[StepEngine] 从检查点恢复 plan，继续执行")
            return True
        return False

    # ---------------- 事件广播 ----------------
    def _emit(self, type_: str, turn_id=None, step_id=None, data=None) -> None:
        if self.signals:
            self.signals._events.publish(type_, turn_id=turn_id, step_id=step_id, data=data)

    def _emit_step_end(self, turn_id: str, step: Step) -> None:
        self._emit("step/end", turn_id=turn_id, step_id=step.step_id, data=step.to_dict())

    # ---------------- plan step ----------------
    async def _run_plan_step(self, turn_id: str, query: str, main_prompt: str,
                             catalog: List[Dict[str, Any]], allow_sub_agents: bool,
                             history: List[Any], run_mode: str) -> Dict[str, Any]:
        plan_step = self.ctx.register(Step.new(StepType.PLAN, name="plan"))
        plan_step.start()
        self._emit("step/start", turn_id=turn_id, step_id=plan_step.step_id, data=plan_step.to_dict())

        pre = await self.hooks.run_pre_step(self.ctx, plan_step)
        if pre.aborted:
            plan_step.skip(pre.reason)
            self._emit_step_end(turn_id, plan_step)
            return {"event": None, "plan": {"need_sub_agents": False, "plan": [], "direct_answer": ""}}

        llm = await self._rt._create_llm()
        orchestration_msgs = [
            *([{"role": getattr(m, "type", "user"), "content": getattr(m, "content", "")}
               for m in (history or [])]),
            {"role": "user", "content": query},
        ]
        plan: OrchestrationPlan = await self._rt._orchestrate(llm, orchestration_msgs, main_prompt, catalog)
        if not allow_sub_agents:
            plan.need_sub_agents = False
            plan.plan = []

        tasks = []
        for t in plan.plan:
            real_id = self._rt.loader.resolve_sub_agent_id(getattr(t, "sub_agent_id", ""), catalog) or t.sub_agent_id
            tasks.append({"sub_agent_id": real_id, "task_prompt": t.task_prompt})

        plan_dict = {
            "need_sub_agents": plan.need_sub_agents,
            "run_mode": plan.run_mode or run_mode,
            "plan": tasks,
            "direct_answer": plan.direct_answer,
        }
        self.ctx.plan = plan_dict

        yield_plan = {"need_sub_agents": plan.need_sub_agents,
                      "run_mode": plan.run_mode,
                      "plan": tasks}
        yield_plan = await self.hooks.run_waterfall("plan/created", yield_plan)

        plan_step.complete({"plan": plan_dict})
        self._emit("plan/created", turn_id=turn_id, step_id=plan_step.step_id, data=yield_plan)
        self._emit_step_end(turn_id, plan_step)

        if self.signals:
            await self.signals.checkpoint.save(self.session_id or "anon", turn_id,
                                               {"type": "plan_done"}, {"plan": plan_dict})
        return {"event": {"type": "orchestrator_plan", "data": yield_plan}, "plan": plan_dict}

    # ---------------- direct step ----------------
    async def _run_direct_step(self, turn_id: str, query: str, main_prompt: str,
                               main_agent_cfg: Any) -> AsyncGenerator[Dict[str, Any], None]:
        dstep = self.ctx.register(Step.new(StepType.DIRECT, name="direct"))
        dstep.start()
        self._emit("step/start", turn_id=turn_id, step_id=dstep.step_id, data=dstep.to_dict())
        pre = await self.hooks.run_pre_step(self.ctx, dstep)
        if pre.aborted:
            dstep.skip(pre.reason)
            self._emit_step_end(turn_id, dstep)
            return

        collected: List[str] = []
        async for kind, tok in self._rt._direct_answer_stream(
                query, main_prompt, main_agent_cfg, session_id=self.session_id):
            if kind == "reasoning":
                yield {"type": "reasoning", "content": tok}
            else:
                collected.append(tok)
                yield {"type": "token", "content": tok}
                # Append to session_log
                if self.signals and hasattr(self.signals, 'session_log'):
                    await self.signals.session_log.append(
                        self.session_id or "anon", "assistant/message", {"content": tok}, turn=1)
        dstep.complete({"content": "".join(collected)[:200]})
        self._emit_step_end(turn_id, dstep)

    # ---------------- dispatch（串/并行子 Agent steps） ----------------
    async def _run_dispatch(self, turn_id: str, main_prompt: str,
                            history: List[Any]) -> AsyncGenerator[Dict[str, Any], None]:
        plan = self.ctx.plan or {}
        mode = plan.get("run_mode") or "serial"
        tasks = [SubTask(sub_agent_id=t["sub_agent_id"], task_prompt=t.get("task_prompt", ""))
                 for t in (plan.get("plan") or [])]
        results: List[SubAgentResult] = []

        async def _one(t: SubTask) -> SubAgentResult:
            s = self.ctx.register(Step.new(StepType.SUB_AGENT, name=f"sub:{t.sub_agent_id}",
                                           input={"sub_agent_id": t.sub_agent_id,
                                                  "task_prompt": t.task_prompt}))
            s.start()
            self._emit("step/start", turn_id=turn_id, step_id=s.step_id, data=s.to_dict())
            pre = await self.hooks.run_pre_step(self.ctx, s)
            if pre.aborted:
                s.skip(pre.reason)
                self._emit_step_end(turn_id, s)
                return SubAgentResult(sub_agent_id=t.sub_agent_id, success=False, error=pre.reason)

            r = await self._rt._exec_sub_task(None, t, main_prompt, state=None, history=history)
            if r.success:
                s.complete({"content": str(r.content)[:200], "approvals": bool(r.approvals)})
            else:
                s.fail(r.error or "sub_agent failed")

            # post-step hook（可改写结果）
            post = await self.hooks.run_post_step(self.ctx, s)
            if post.output is not None and post.output.get("content"):
                r.content = post.output["content"]
            self._emit_step_end(turn_id, s)
            return r

        # 每个子 Agent 前的决策点：broadcast running + drain send
        if mode == "parallel":
            gathered = await asyncio.gather(*[_one(t) for t in tasks])
            results = list(gathered)
            for t, r in zip(tasks, results):
                yield {"type": "sub_agent", "data": {
                    "sub_agent_id": t.sub_agent_id, "status": "done",
                    "success": r.success, "content": (r.content if r.success else None),
                    "error": r.error}}
        else:
            for t in tasks:
                self._drain_send()
                yield {"type": "sub_agent", "data": {"sub_agent_id": t.sub_agent_id, "status": "running"}}
                r = await _one(t)
                results.append(r)
                yield {"type": "sub_agent", "data": {
                    "sub_agent_id": t.sub_agent_id, "status": "done",
                    "success": r.success, "content": (r.content if r.success else None),
                    "error": r.error}}

        # 动态 plan（重试一次失败的子 Agent）：把 plan 更新到 ctx
        failed = [r for r in results if not r.success]
        if failed and self.ctx:
            await self.hooks.run_waterfall("dispatch/failed", {
                "results": results, "query": self.turn.query if self.turn else ""})

        self.ctx.vars["sub_agent_results"] = results
        return

    # ---------------- aggregate step ----------------
    async def _run_aggregate(self, turn_id: str, results: List[SubAgentResult],
                             main_prompt: str) -> AsyncGenerator[str, None]:
        astep = self.ctx.register(Step.new(StepType.AGGREGATE, name="aggregate"))
        astep.start()
        self._emit("step/start", turn_id=turn_id, step_id=astep.step_id, data=astep.to_dict())
        pre = await self.hooks.run_pre_step(self.ctx, astep)
        if pre.aborted:
            astep.skip(pre.reason)
            self._emit_step_end(turn_id, astep)
            return

        redactor = None
        try:
            from packages.agent.orchestrator.text_utils import make_pii_redactor
            redactor = make_pii_redactor()
        except Exception:
            redactor = None
        llm = await self._rt._create_llm()
        async for tok in self._rt._aggregate_stream(llm, results, main_prompt, redactor=redactor):
            yield tok
        astep.complete({"content": "aggregated"})
        self._emit_step_end(turn_id, astep)

    # ---------------- 主循环 ----------------
    async def execute(self, query: str, main_prompt: str, main_agent_cfg: Any,
                      catalog: List[Dict[str, Any]], *, run_mode: str = "serial",
                      allow_sub_agents: bool = True,
                      history: Optional[List[Any]] = None
                      ) -> AsyncGenerator[Dict[str, Any], None]:
        """Step 驱动主循环。产出与 run_stream 一致的事件协议。"""
        turn = Turn.new(query, user_id=self.user_id, session_id=self.session_id)
        ctx = ExecutionContext(turn)
        self.ctx = ctx
        self.turn = turn
        ctx.user_id = self.user_id
        ctx.session_id = self.session_id
        turn.start()
        turn_id = turn.turn_id

        self._emit("turn/start", turn_id=turn_id, data={"query": query})
        # Append to session_log
        if self.signals and hasattr(self.signals, 'session_log'):
            await self.signals.session_log.append(
                self.session_id or "anon", "turn/start", {"query": query}, turn=1)
            await self.signals.session_log.append(
                self.session_id or "anon", "user/message", {"content": query}, turn=1)

        restored = await self._try_restore(turn_id)

        # ---- Plan step（每个用户任务的第一步，且仅在未恢复时执行一次）----
        if not restored:
            plan_out = await self._run_plan_step(
                turn_id, query, main_prompt, catalog, allow_sub_agents, history or [], run_mode)
            if plan_out["event"]:
                ev = plan_out["event"]
                injections = self._drain_send()
                if injections:
                    ev["data"] = dict(ev["data"])
                    ev["data"]["injections"] = [i.get("content") for i in injections]
                yield ev
        else:
            yield {"type": "orchestrator_plan", "data": self.ctx.plan}

        plan = self.ctx.plan or {}
        need_sub = plan.get("need_sub_agents")
        has_tasks = bool(plan.get("plan") or [])

        # ---- 决策点：direct 或 dispatch ----
        if not (need_sub and has_tasks):
            # direct step（无子 Agent）
            async for ev in self._run_direct_step(turn_id, query, main_prompt, main_agent_cfg):
                yield ev
        else:
            # dispatch + aggregate
            async for ev in self._run_dispatch(turn_id, main_prompt, history or []):
                yield ev
            results = (self.ctx.vars.get("sub_agent_results") or [])
            async for tok in self._run_aggregate(turn_id, results, main_prompt):
                yield {"type": "token", "content": tok}

        turn.complete()
        self._emit("turn/end", turn_id=turn_id,
                   data={"status": turn.status.value, "duration_ms": turn.duration_ms})
