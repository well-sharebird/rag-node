"""执行框架测试：验证 Step 模型、结构化事件流、钩子系统、事件溯源、生命周期管理。"""
import asyncio
import sys
import types

import pytest

# 隔离 langchain 依赖（若不存在）
for _mod in ("langchain.agents.middleware", "langchain", "langchain_core",
             "langgraph", "sqlalchemy", "packages.agent.core.harness"):
    try:
        __import__(_mod)
    except Exception:
        sys.modules.setdefault(_mod, types.ModuleType(_mod))

from packages.agent.execution.steps import (
    ExecutionContext, Step, StepStatus, StepType, Turn, TurnStatus,
)
from packages.agent.execution.events import ExecutionEventType
from packages.agent.execution.hooks import AbortStep, HookRegistry, HookResult
from packages.agent.execution.sourcing import (
    EventSourcedState, ExecutionCheckpoint, MemoryStore, SessionLog,
)
from packages.agent.execution.lifecycle import (
    AgentRegistry, AgentState, AgentStatus, SessionManager,
)
from packages.agent.execution.runner import StepExecutionRuntime


# ============================================================================
# P0-1: Step / Turn 执行模型
# ============================================================================
class TestStepModel:
    async def test_step_lifecycle(self):
        step = Step.new(StepType.PLAN, name="plan")
        assert step.status == StepStatus.PENDING
        step.start()
        assert step.status == StepStatus.RUNNING
        await asyncio.sleep(0.01)
        step.complete({"plan": []})
        assert step.status == StepStatus.DONE
        assert step.duration_ms > 0
        assert step.to_dict()["type"] == "plan"

    async def test_step_fail_skip_cancel(self):
        s = Step.new(StepType.DISPATCH, name="d")
        s.fail("boom")
        assert s.status == StepStatus.FAILED
        s2 = Step.new(StepType.CUSTOM, name="c")
        s2.skip("reason")
        assert s2.status == StepStatus.SKIPPED
        s3 = Step.new(StepType.TOOL, name="t")
        s3.cancel("user")
        assert s3.status == StepStatus.CANCELLED

    async def test_turn_aggregates_steps(self):
        turn = Turn.new("你好", user_id=1, session_id="s1")
        turn.start()
        s1 = Step.new(StepType.PLAN)
        turn.add_step(s1)
        s2 = Step.new(StepType.AGGREGATE)
        turn.add_step(s2)
        turn.complete()
        assert turn.status == TurnStatus.DONE
        assert turn.total_steps() == 2
        assert turn.duration_ms >= 0
        assert turn.to_dict()["step_count"] == 2

    async def test_context_registers_steps(self):
        turn = Turn.new("q")
        ctx = ExecutionContext(turn)
        st = ctx.register(Step.new(StepType.PLAN))
        assert st in turn.steps
        assert ctx.current_step is st


# ============================================================================
# P0-4 / P1: 结构化事件流
# ============================================================================
class TestEventStream:
    async def test_publish_drain(self):
        stream = __import__("packages.agent.execution.events", fromlist=["ExecutionEventStream"]).ExecutionEventStream()
        stream.publish(ExecutionEventType.TURN_START, turn_id="t1", data={"q": 1})
        stream.publish("custom/event", turn_id="t1")
        ev = stream.try_get()
        assert ev is not None
        assert ev.type == "turn/start"
        d = ev.to_dict()
        assert d["turn_id"] == "t1"
        ev2 = stream.try_get()
        assert ev2.type == "custom/event"
        assert stream.try_get() is None


# ============================================================================
# P1: 钩子系统
# ============================================================================
class TestHooks:
    async def _mk_ctx(self):
        turn = Turn.new("q")
        return ExecutionContext(turn)

    async def test_pre_step_rewrites_input(self):
        reg = HookRegistry()
        async def rewrite(ctx, step):
            return HookResult(input={**step.input, "rewritten": True})
        reg.add_pre_step(rewrite)
        ctx = await self._mk_ctx()
        step = Step.new(StepType.PLAN, name="p", input={"a": 1})
        r = await reg.run_pre_step(ctx, step)
        assert r.aborted is False
        assert r.input["rewritten"] is True
        assert step.input["rewritten"] is True

    async def test_pre_step_abort(self):
        reg = HookRegistry()
        async def deny(ctx, step):
            return HookResult(aborted=True, reason="denied")
        reg.add_pre_step(deny)
        ctx = await self._mk_ctx()
        step = Step.new(StepType.DIRECT, name="d")
        r = await reg.run_pre_step(ctx, step)
        assert r.aborted is True
        assert step.status == StepStatus.SKIPPED

    async def test_post_step_rewrites_output(self):
        reg = HookRegistry()
        async def redact(ctx, step):
            out = dict(step.output or {})
            out["content"] = "***"
            return HookResult(output=out)
        reg.add_post_step(redact)
        ctx = await self._mk_ctx()
        step = Step.new(StepType.SUB_AGENT, name="s")
        step.complete({"content": "secret"})
        r = await reg.run_post_step(ctx, step)
        assert r.output["content"] == "***"
        assert step.output["content"] == "***"

    async def test_waterfall_chains(self):
        reg = HookRegistry()
        reg.add_waterfall("agent/request", lambda p: {**p, "n": p.get("n", 0) + 1})
        reg.add_waterfall("agent/request", lambda p: {**p, "n": p.get("n", 0) + 1})
        ctx = await self._mk_ctx()
        out = await reg.run_waterfall("agent/request", {"x": 1})
        assert out["n"] == 2

    async def test_remove_hook(self):
        reg = HookRegistry()
        async def h(ctx, step):
            return None
        reg.add_pre_step(h)
        assert len(reg.pre_step) == 1
        reg.remove(h)
        assert len(reg.pre_step) == 0


# ============================================================================
# P1: 事件溯源 / 会话日志 / 检查点
# ============================================================================
class TestSourcing:
    async def test_session_log_derive_messages(self):
        log = SessionLog()
        await log.append("s1", "user/message", {"content": "hi"}, turn=1)
        await log.append("s1", "assistant/message", {"content": "hello", "reasoning": "think"}, turn=1)
        await log.append("s1", "tool/result", {"content": "res"}, turn=1)
        msgs = await log.derive_messages("s1")
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "hi"}
        assert "[reasoning] think" in msgs[1]["content"]

    async def test_event_sourced_state_replay(self):
        log = SessionLog()
        await log.append("s1", "plan/created", {"plan": {"run": "serial"}}, turn=1)
        await log.append("s1", "sub_agent/done", {"sub_agent_id": "a", "success": True}, turn=1)
        src = EventSourcedState(log)
        state = await src.replay("s1")
        assert state["plan"]["run"] == "serial"
        assert state["sub_agent_results"][0]["sub_agent_id"] == "a"

    async def test_checkpoint_save_restore(self):
        cp = ExecutionCheckpoint()
        await cp.save("s1", "turn1", {"step": 3}, {"plan": {}})
        data = await cp.restore("s1", "turn1")
        assert data["step"]["step"] == 3
        await cp.clear("s1", "turn1")
        assert await cp.restore("s1", "turn1") is None


# ============================================================================
# P2: 生命周期
# ============================================================================
class TestLifecycle:
    async def test_agent_state_machine(self):
        agent = AgentState("a1")
        assert agent.is_idle
        turn_id = agent.begin_turn()
        assert agent.is_running
        assert agent.current_turn == turn_id
        agent.end_turn()
        assert agent.is_idle
        agent.begin_turn()
        agent.cancel("user cancelled")
        assert agent.is_idle

    async def test_agent_begin_turn_while_running_raises(self):
        agent = AgentState("a2")
        agent.begin_turn()
        with pytest.raises(RuntimeError):
            agent.begin_turn()

    async def test_agent_dispose(self):
        agent = AgentState("a3")
        agent.dispose()
        assert agent.status == AgentStatus.DISPOSED
        with pytest.raises(RuntimeError):
            agent.begin_turn()

    async def test_registry_create_get_dispose(self):
        reg = AgentRegistry()
        a = reg.create("x")
        assert reg.get("x") is a
        with pytest.raises(ValueError):
            reg.create("x")
        reg.dispose("x")
        assert reg.get("x") is None

    async def test_session_fork(self):
        log = SessionLog()
        await log.append("src", "user/message", {"content": "hi"}, turn=1, step=1)
        await log.append("src", "user/message", {"content": "after"}, turn=1, step=2)
        mgr = SessionManager(log)
        child = await mgr.fork("src", boundary_step=1)
        events = await log.events(child)
        assert len(events) == 1
        assert mgr.parent(child) == "src"


# ============================================================================
# 集成: StepExecutionRuntime（含 P0-2 send、P0-3 update_plan）
# ============================================================================
class TestStepRuntime:
    async def _make_fake_orchestrator(self, events):
        class FakeOrch:
            def __init__(self, events):
                self.events = events
            async def run_stream(self, query, **kw):
                for e in self.events:
                    yield e
        return FakeOrch(events), []

    async def test_runtime_emits_structured_events_and_logs(self):
        orch, _ = await self._make_fake_orchestrator([
            {"type": "orchestrator_plan", "data": {"need_sub_agents": True, "plan": []}},
            {"type": "sub_agent", "data": {"sub_agent_id": "a", "status": "running"}},
            {"type": "sub_agent", "data": {"sub_agent_id": "a", "status": "done", "success": True, "content": "ok"}},
            {"type": "token", "data": {"content": "最终"}},
        ])
        rt = StepExecutionRuntime(orch, session_id="s1", user_id=1)
        collected = [ev async for ev in rt.execute_stream("问题")]
        # 扁平事件透视
        assert any(e["type"] == "orchestrator_plan" for e in collected)
        assert any(e["type"] == "token" for e in collected)
        # turn 建模
        assert rt.turn is not None
        assert rt.turn.status == TurnStatus.DONE
        assert rt.turn.total_steps() >= 1
        # 事件流
        evs = []
        while True:
            e = rt.drain()
            if e is None:
                break
            evs.append(e)
        types = {e.type for e in evs}
        assert "turn/start" in types
        assert "turn/end" in types
        assert "plan/created" in types
        # 会话日志
        log_msgs = await rt.session_log.derive_messages("s1")
        assert any(m["role"] == "user" for m in log_msgs)
        assert any("最终" in m["content"] for m in log_msgs)
        # 检查点
        cp = await rt.checkpoint.restore("s1", rt.turn.turn_id)
        assert cp is not None

    async def test_runtime_send_and_update_plan(self):
        orch, _ = await self._make_fake_orchestrator([
            {"type": "orchestrator_plan", "data": {"need_sub_agents": True, "plan": [{"sub_agent_id": "a", "task_prompt": "t"}]}},
            {"type": "token", "data": {"content": "x"}},
        ])
        rt = StepExecutionRuntime(orch, session_id="s1")
        await asyncio.sleep(0)
        # execute 过程中外部调用
        async def _drive():
            async for _ in rt.execute_stream("q"):
                pass
        task = asyncio.create_task(_drive())
        await asyncio.sleep(0.05)
        # send 追加指令
        rt.send("再优化一下")
        # 读取并更新 plan
        plan = rt.get_plan()
        if plan:
            rt.update_plan({**plan, "run_mode": "parallel"})
        await task
        # 检查点确认
        assert rt.turn.status == TurnStatus.DONE


# ============================================================================
# 集成: ExecutionOrchestrator 经由 StepExecutionRuntime 执行，并暴露新能力
# ============================================================================
class TestExecutionOrchestratorIntegration:
    async def test_execute_stream_routes_through_step_runtime(self):
        from packages.agent.integration.execution_chain import ExecutionOrchestrator

        class FakeDB:
            pass

        orch = ExecutionOrchestrator(FakeDB(), user_id=1)
        events_out = [
            {"type": "orchestrator_plan", "data": {"need_sub_agents": False, "plan": [], "direct_answer": "hi"}},
            {"type": "token", "content": "Hello "},
            {"type": "token", "content": "world"},
        ]

        class FakeRuntime:
            async def run_stream(self, query, **kw):
                for e in events_out:
                    yield e

        # 替换内部 runtime 为假实现
        orch._runtime = FakeRuntime()
        await orch.start()
        try:
            collected = [e async for e in orch.execute_stream("test", session_id="test")]
        finally:
            await orch.stop()
        assert any(e.get("type") == "token" for e in collected)
        # Step 门面已挂载
        assert orch.execution is not None
        assert orch.execution.turn is not None
        # 会话日志记录了 user 与 assistant 消息
        msgs = await orch.execution.session_log.derive_messages("test")
        assert any(m["role"] == "user" for m in msgs)
        assert any(m["role"] == "assistant" for m in msgs)

    async def test_execution_hooks_api(self):
        from packages.agent.integration.execution_chain import ExecutionOrchestrator

        class FakeDB:
            pass

        orch = ExecutionOrchestrator(FakeDB(), user_id=1)
        # 注册钩子（P1 对外 API）
        seen = []
        async def pre_hook(ctx, step):
            seen.append(("pre", step.type.value))
            return None
        async def post_hook(ctx, step):
            seen.append(("post", step.type.value))
            return None
        orch.add_pre_step_hook(pre_hook)
        orch.add_post_step_hook(post_hook)
        orch.add_waterfall("plan/created", lambda p: p)

        assert orch._execution_hooks is not None
        assert len(orch._execution_hooks.pre_step) == 1

        class FakeRuntime:
            async def run_stream(self, query, **kw):
                yield {"type": "orchestrator_plan", "data": {"need_sub_agents": False, "plan": []}}
                yield {"type": "token", "content": "ok"}

        orch._runtime = FakeRuntime()
        await orch.start()
        try:
            [e async for e in orch.execute_stream("q")]
        finally:
            await orch.stop()
        # pre 钩子应被执行（plan step 至少一次）
        assert len(seen) >= 1
        assert seen[0][0] == "pre"
