"""StepDrivenEngine 测试：验证 Step 驱动执行（而非固定流水线）。

用 fake runtime 提供 _orchestrate/_direct_answer_stream/_exec_sub_task/_aggregate_stream，
聚焦验证 Step 引擎的决策行为：钩子真实影响执行、动态 plan、send 注入、检查点恢复。
"""
import asyncio
import sys
from unittest.mock import MagicMock

sys.modules['langchain.agents.middleware'] = MagicMock()

import pytest

from packages.agent.execution.step_engine import StepDrivenEngine
from packages.agent.execution.hooks import HookRegistry, HookResult
from packages.agent.execution.steps import ExecutionContext, Step, StepStatus
from packages.agent.execution.sourcing import MemoryStore, ExecutionCheckpoint, SessionLog
from packages.agent.execution.lifecycle import AgentState
from packages.agent.execution.runner import StepExecutionRuntime
from packages.agent.execution.events import ExecutionEventStream


# ---------------- fake runtime ----------------
class FakePlan:
    def __init__(self, need, run_mode="serial", tasks=(), direct=""):
        self.need_sub_agents = need
        self.run_mode = run_mode
        self.plan = tasks
        self.direct_answer = direct


class FakeTask:
    def __init__(self, sub_agent_id, task_prompt):
        self.sub_agent_id = sub_agent_id
        self.task_prompt = task_prompt


class FakeResult:
    def __init__(self, success=True, content="", error=None, approvals=None, sub_agent_id=None):
        self.success = success
        self.content = content
        self.error = error
        self.approvals = approvals or []
        self.sub_agent_id = sub_agent_id


class FakeLoader:
    def __init__(self, catalog):
        self._cat = catalog

    def resolve_sub_agent_id(self, sid, catalog):
        return sid


class FakeRuntime:
    def __init__(self, plan):
        self._plan = plan
        self.loader = FakeLoader([])
        self.plan_calls = 0

    async def _create_llm(self):
        return MagicMock()

    async def _orchestrate(self, llm, msgs, main_prompt, catalog):
        self.plan_calls += 1
        return self._plan

    async def _direct_answer_stream(self, query, main_prompt, cfg, session_id=None):
        yield ("content", "direct answer tokens")

    async def _exec_sub_task(self, llm, sub_task, main_prompt, state=None, history=None):
        return FakeResult(success=True, content=f"result:{sub_task.sub_agent_id}")

    async def _aggregate_stream(self, llm, results, main_prompt, redactor=None):
        yield "聚合"
        for r in results:
            yield f"[{r.sub_agent_id}={r.content}]"


# ---------------- helpers ----------------
def mk_signals(session_id="s1"):
    """构造带 signals 的轻量对象（沿用 StepExecutionRuntime 的子系统）。"""
    sig = StepExecutionRuntime.__new__(StepExecutionRuntime)
    sig.session_id = session_id
    sig.agent = AgentState("main")
    sig.store = MemoryStore()
    sig.checkpoint = ExecutionCheckpoint(sig.store)
    sig.session_log = SessionLog(sig.store)
    sig._events = ExecutionEventStream()
    return sig


async def run_events(engine, **kw):
    return [e async for e in engine.execute("问题", "你是助手", None, [], **kw)]


class TestStepEngineDirect:
    async def test_direct_path_emits_plan_then_tokens(self):
        rt = FakeRuntime(FakePlan(need=False, direct="x"))
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=HookRegistry(), signals=sig, session_id=sig.session_id)
        evs = await run_events(engine)
        types = [e["type"] for e in evs]
        assert "orchestrator_plan" in types
        assert "token" in types
        # Turn 已建模
        assert engine.turn is not None
        assert engine.turn.status.value == "done"
        # plan step 已驱动
        plan_steps = [s for s in engine.turn.steps if s.type.value == "plan"]
        assert plan_steps and plan_steps[0].status == StepStatus.DONE

    async def test_dispatch_path_emits_sub_agent_events_and_aggregate(self):
        tasks = [FakeTask("a", "t1"), FakeTask("b", "t2")]
        rt = FakeRuntime(FakePlan(need=True, run_mode="serial", tasks=tasks))
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=HookRegistry(), signals=sig, session_id=sig.session_id)
        evs = await run_events(engine)
        sub_done = [e for e in evs if e.get("type") == "sub_agent" and e["data"].get("status") == "done"]
        assert len(sub_done) == 2
        # 有 sub_agent step
        sub_steps = [s for s in engine.turn.steps if s.type.value == "sub_agent"]
        assert len(sub_steps) == 2

    async def test_parallel_mode_runs_all(self):
        tasks = [FakeTask("a", "t1"), FakeTask("b", "t2")]
        rt = FakeRuntime(FakePlan(need=True, run_mode="parallel", tasks=tasks))
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=HookRegistry(), signals=sig, session_id=sig.session_id)
        evs = await run_events(engine)
        sub_done = [e for e in evs if e.get("type") == "sub_agent" and e["data"].get("status") == "done"]
        assert len(sub_done) == 2


class TestStepEngineHooks:
    async def test_pre_step_hook_can_block_sub_agent(self):
        rt = FakeRuntime(FakePlan(need=True, tasks=[FakeTask("blocked", "t")]))
        hooks = HookRegistry()
        async def deny(ctx, step):
            if step.type.value == "sub_agent" and step.input and step.input.get("sub_agent_id") == "blocked":
                return HookResult(aborted=True, reason="blocked agent")
            return None
        hooks.add_pre_step(deny)
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=hooks, signals=sig)
        evs = await run_events(engine)
        # 被拒的子 Agent 应产出 done(success=False)
        blocked = [e for e in evs if e.get("type") == "sub_agent"
                   and e["data"].get("sub_agent_id") == "blocked" and e["data"].get("status") == "done"]
        assert blocked and blocked[0]["data"].get("success") is False

    async def test_waterfall_rewrites_plan(self):
        rt = FakeRuntime(FakePlan(need=False, direct="x"))
        hooks = HookRegistry()
        seen = {}
        hooks.add_waterfall("plan/created", lambda p: {**p, "extra": "added"})
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=hooks, signals=sig)
        evs = await run_events(engine)
        plan_ev = [e for e in evs if e.get("type") == "orchestrator_plan"][0]
        assert plan_ev["data"].get("extra") == "added"


class TestStepEngineSend:
    async def test_send_injection_consumed_at_decision_point(self):
        rt = FakeRuntime(FakePlan(need=True, tasks=[FakeTask("a", "t")]))
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=HookRegistry(), signals=sig, session_id=sig.session_id)
        # 在派发前通过 inbox 注入指令
        sig.agent.send({"type": "inject", "content": "优先处理安全", "by": "user"})

        async def _drive():
            async for _ in engine.execute("问题", "你是助手", None, []):
                pass
        task = asyncio.create_task(_drive())
        await asyncio.sleep(0.05)
        # 决策点已消费（inbox 清空）
        assert sig.agent.inbox.empty()
        await task


class FakeRuntimeWithFail:
    """首次子 Agent 失败，用于验证重试类动态 plan。"""
    def __init__(self):
        self.loader = FakeLoader([])
        self.calls = {"a": 0}

    async def _create_llm(self):
        return MagicMock()

    async def _orchestrate(self, llm, msgs, main_prompt, catalog):
        return FakePlan(need=True, tasks=[FakeTask("a", "t")])

    async def _direct_answer_stream(self, query, main_prompt, cfg, session_id=None):
        yield ("content", "direct")

    async def _exec_sub_task(self, llm, sub_task, main_prompt, state=None, history=None):
        self.calls["a"] += 1
        return FakeResult(success=False, error="transient failure")

    async def _aggregate_stream(self, llm, results, main_prompt, redactor=None):
        yield "聚合失败处理"


class TestStepEngineDynamicPlan:
    async def test_dispatch_failed_waterfall_evaluated(self):
        rt = FakeRuntimeWithFail()
        hooks = HookRegistry()
        calls = []
        hooks.add_waterfall("dispatch/failed", lambda p: calls.append(p) or p)
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=hooks, signals=sig)
        evs = await run_events(engine)
        # 失败信息进入 waterfall 评估点，外部可据此改 plan 重试
        assert len(calls) == 1
        failed = [r for r in calls[0].get("results", []) if not r.success]
        assert len(failed) == 1
        # 子 Agent step 标记为 failed
        sub_steps = [s for s in engine.turn.steps if s.type.value == "sub_agent"]
        assert sub_steps[0].status == StepStatus.FAILED


class TestStepEngineCheckpoint:
    async def test_checkpoint_saved_after_plan(self):
        rt = FakeRuntime(FakePlan(need=False, direct="x"))
        sig = mk_signals()
        engine = StepDrivenEngine(rt, hooks=HookRegistry(), signals=sig, session_id=sig.session_id)
        evs = await run_events(engine)
        # 计划完成后保存了检查点
        cp = await sig.checkpoint.restore(sig.session_id, engine.turn.turn_id)
        assert cp is not None
        assert cp["state"]["plan"]["need_sub_agents"] is False
