"""
Supervisor 编排图测试（LangGraph 状态机按 OrchestratorState 流转）

用 FakeRuntime 驱动真 build_supervisor_graph，断言：
    - plan →(sub_tasks 空)→ direct / plan →(有)→ dispatch → aggregate 路由
    - 节点只返回变更键、OrchestratorState 终态正确
    - dispatch 传 per-task 私有 dict，图上 temp_sub_config 终态 None
    - 事件经 sink 顺序产出（orchestrator_plan → sub_agent → token；审批 approval_required）
    - run 用的 quick 直答（plan.direct_answer）与 run_stream 用的 graph 直答（全图流式）
"""
import asyncio
import pytest

from packages.agent.orchestrator.state import OrchestrationPlan, SubAgentResult, SubTask
from packages.agent.orchestrator.supervisor import NoopSink, build_supervisor_graph


def _initial_state(**over):
    s = {
        "messages": [{"role": "user", "content": "hi"}],
        "session_id": "s1",
        "trace_id": "t1",
        "main_agent_config": {"agent_id": "main"},
        "temp_sub_config": None,
        "sub_tasks": [],
        "sub_agent_results": [],
        "final_answer": None,
        "error": None,
    }
    s.update(over)
    return s


class FakeRuntime:
    """最小 runtime：节点用到的所有方法都打桩，记录 dipatch 收到的 state。"""

    def __init__(self, plan, sub_result=None, direct_tokens=(), aggregate_tokens=()):
        self.plan = plan
        self.sub_result = sub_result or SubAgentResult(sub_agent_id="sub-a", content="ok")
        self.direct_tokens = list(direct_tokens)
        self.aggregate_tokens = list(aggregate_tokens)
        self.dispatch_state_seen = None
        self.dispatch_history_seen = None
        self.orchestration_msgs = None

    async def _create_llm(self):
        return "llm"

    async def _orchestrate(self, llm, messages, main_prompt, catalog):
        self.orchestration_msgs = messages
        return self.plan

    class _Loader:
        def resolve_sub_agent_id(self, agent_id, catalog):
            return None
    loader = _Loader()

    async def _direct_answer_stream(self, query, main_prompt, main_agent_cfg, session_id=None):
        for tok in self.direct_tokens:
            # 支持 (kind, text) 元组（含 reasoning），或纯字符串（视为 content）
            yield tok if isinstance(tok, tuple) else ("content", tok)

    async def _exec_sub_task(self, llm, sub_task, main_prompt, state=None, history=None):
        self.dispatch_state_seen = state
        self.dispatch_history_seen = history
        return self.sub_result

    async def _aggregate_stream(self, llm, results, main_prompt, redactor=None):
        for tok in self.aggregate_tokens:
            yield tok

    @staticmethod
    def _redact_block(redactor, text):
        return text if text is not None else ""


async def _run(runtime, *, strategy="graph", allow_sub_agents=True, history=None):
    sink = asyncio.Queue()
    g = build_supervisor_graph(
        runtime, sink=sink, query="hi", main_prompt="你是主", main_agent_cfg=object(),
        catalog=[], run_mode="serial", allow_sub_agents=allow_sub_agents,
        session_id="s1", redactor=None, direct_strategy=strategy, history=history,
    )
    final = await g.ainvoke(_initial_state(), config=None)
    events = []
    while not sink.empty():
        events.append(sink.get_nowait())
    return events, final


@pytest.mark.asyncio
async def test_route_direct_quick_returns_plan_answer():
    rt = FakeRuntime(OrchestrationPlan(need_sub_agents=False, plan=[],
                                       direct_answer="快速直答", run_mode="serial"))
    events, final = await _run(rt, strategy="quick")
    assert final["final_answer"] == "快速直答"
    assert final["sub_tasks"] == [] and final["sub_agent_results"] == []
    assert [e["type"] for e in events] == ["orchestrator_plan"]
    assert events[0]["data"]["need_sub_agents"] is False


@pytest.mark.asyncio
async def test_route_direct_graph_streams_tokens():
    rt = FakeRuntime(OrchestrationPlan(need_sub_agents=False, plan=[]),
                     direct_tokens=["你", "好"])
    events, final = await _run(rt, strategy="graph")
    assert final["final_answer"] == "你好"
    assert [e["type"] for e in events] == ["orchestrator_plan", "token", "token"]
    assert [e["content"] for e in events[1:]] == ["你", "好"]


@pytest.mark.asyncio
async def test_route_direct_graph_reasoning_and_answer_events():
    # 直答流产生的元组：reasoning 独立成 reasoning 事件，content 才进 token 事件与 final_answer
    rt = FakeRuntime(OrchestrationPlan(need_sub_agents=False, plan=[]),
                     direct_tokens=[("reasoning", "想"), ("content", "答"),
                                    ("reasoning", "再想"), ("content", "案")])
    events, final = await _run(rt, strategy="graph")
    assert final["final_answer"] == "答案"  # 仅累计 content
    assert [e["type"] for e in events] == ["orchestrator_plan", "reasoning", "token", "reasoning", "token"]
    assert [e for e in events if e["type"] == "reasoning"] == [
        {"type": "reasoning", "content": "想"}, {"type": "reasoning", "content": "再想"}]
    assert [e["content"] for e in events if e["type"] == "token"] == ["答", "案"]


@pytest.mark.asyncio
async def test_route_dispatch_aggregate():
    plan = OrchestrationPlan(
        need_sub_agents=True, run_mode="serial",
        plan=[SubTask(sub_agent_id="sub-a", task_prompt="do it")])
    sub = SubAgentResult(sub_agent_id="sub-a", success=True, content="ok")
    rt = FakeRuntime(plan, sub_result=sub, aggregate_tokens=["聚合"])
    events, final = await _run(rt)

    types = [e["type"] for e in events]
    assert types == ["orchestrator_plan", "sub_agent", "sub_agent", "token"]
    assert events[1]["data"]["status"] == "running"
    assert events[2]["data"]["status"] == "done" and events[2]["data"]["success"] is True
    assert events[3]["content"] == "聚合"

    assert final["sub_tasks"] == [{"sub_agent_id": "sub-a", "task_prompt": "do it"}]
    assert final["sub_agent_results"][0]["content"] == "ok"
    assert final["final_answer"] == "聚合"
    # #7：dispatch 接真实 OrchestratorState（非一次性哑元），temp_sub_config 终态仍清空
    assert final["temp_sub_config"] is None
    assert rt.dispatch_state_seen.get("session_id") == "s1"
    assert rt.dispatch_state_seen.get("messages") == [{"role": "user", "content": "hi"}]
    assert "temp_sub_config" in rt.dispatch_state_seen


@pytest.mark.asyncio
async def test_approval_event_emitted():
    plan = OrchestrationPlan(
        need_sub_agents=True, run_mode="serial",
        plan=[SubTask(sub_agent_id="sub-a", task_prompt="x")])
    sub = SubAgentResult(sub_agent_id="sub-a", content="待审批",
                         approvals=[{"tool": "save_workspace_file", "request_id": "r1"}])
    rt = FakeRuntime(plan, sub_result=sub, aggregate_tokens=["聚合"])
    events, _ = await _run(rt)

    types = [e["type"] for e in events]
    assert types == ["orchestrator_plan", "sub_agent", "approval_required", "sub_agent", "token"]
    # serial：running 事件后先发审批，再发 done
    assert events[2]["type"] == "approval_required"
    assert events[2]["data"]["pending"][0]["request_id"] == "r1"
    assert events[3]["type"] == "sub_agent" and events[3]["data"]["status"] == "done"


@pytest.mark.asyncio
async def test_noop_sink_discards_and_parallel_mode():
    plan = OrchestrationPlan(
        need_sub_agents=True, run_mode="parallel",
        plan=[SubTask(sub_agent_id="sub-a", task_prompt="a"),
              SubTask(sub_agent_id="sub-b", task_prompt="b")])
    rt = FakeRuntime(plan, sub_result=SubAgentResult(sub_agent_id="sub-a", content="ok"),
                     aggregate_tokens=["聚合"])
    g = build_supervisor_graph(
        rt, sink=NoopSink(), query="hi", main_prompt="你是主", main_agent_cfg=object(),
        catalog=[], run_mode="parallel", allow_sub_agents=True, session_id=None,
        redactor=None, direct_strategy="graph",
    )
    final = await g.ainvoke(_initial_state(), config=None)
    assert final["final_answer"] == "聚合"
    assert len(final["sub_agent_results"]) == 2


@pytest.mark.asyncio
async def test_memory_reinjected_to_plan_and_dispatch():
    """#5：会话历史回灌到编排——plan_node 看到 history+query，dispatch 透传 history。"""
    from types import SimpleNamespace

    hist = [SimpleNamespace(type="user", content="之前的对话"),
            SimpleNamespace(type="assistant", content="之前的回答")]
    plan = OrchestrationPlan(
        need_sub_agents=True, run_mode="serial",
        plan=[SubTask(sub_agent_id="sub-a", task_prompt="do it")])
    rt = FakeRuntime(plan, aggregate_tokens=["聚合"])
    await _run(rt, history=hist)

    assert rt.orchestration_msgs == [
        {"role": "user", "content": "之前的对话"},
        {"role": "assistant", "content": "之前的回答"},
        {"role": "user", "content": "hi"},
    ]
    assert rt.dispatch_history_seen is hist
