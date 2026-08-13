"""
Phase 4 #1: 统一 OrchestratorState 落地测试

验证 run_stream 真正承载统一 State（而非纯函数式局部变量）：
    - 主 Agent 配置快照（main_agent_config）
    - 子临时配置生命周期（temp_sub_config 进入填/退出清空）
    - 子任务/结果/终答写回（sub_tasks / sub_agent_results / final_answer）
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from packages.agent.orchestrator.graph import OrchestratorRuntime
from packages.agent.orchestrator.state import OrchestrationPlan, SubAgentResult, SubTask


class TestSnapshotMainConfig:

    def test_dataclass_snapshot(self):
        from dataclasses import make_dataclass

        Cfg = make_dataclass("Cfg", [("agent_id", str), ("system_prompt", str),
                                     ("tools_whitelist", list), ("inert", str)])
        cfg = Cfg(agent_id="main", system_prompt="soul+claude", tools_whitelist=["a"], inert="no")
        snap = OrchestratorRuntime._snapshot_main_config(cfg)
        assert snap["agent_id"] == "main"
        assert snap["system_prompt"] == "soul+claude"
        assert "inert" not in snap  # 非保留字段不进入 State


class TestTempConfigLifecycle:

    @pytest.mark.asyncio
    async def test_temp_sub_config_set_then_cleared(self):
        rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
        rt.user_id = 1
        rt.session_id = None

        from packages.agent.orchestrator.agent_loader import LoadedAgentConfig
        cfg = LoadedAgentConfig(agent_id="sub-a", name="SubA",
                                system_prompt="sys", tools_whitelist=[],
                                sandbox_policy={}, require_approval_tools=[],
                                max_step=3, inherit_main_context=False)

        captured = {}

        async def fake_run(sub_llm, tools, sub_system, sub_security, c, task_prompt, sandbox_workdir=None):
            captured["temp"] = dict(state)["temp_sub_config"]
            return SubAgentResult(sub_agent_id="sub-a", success=True, content="done")

        rt.loader = AsyncMock()  # placeholder, replaced below
        rt._create_llm = AsyncMock(return_value="llm")
        rt._load_sub_tools = lambda wl: []
        rt._run_sub_agent_graph = fake_run

        class Loader:
            async def load_sub_agent(self, agent_id):
                return cfg
        rt.loader = Loader()

        state = {"temp_sub_config": "sentinel"}
        res = await rt._exec_sub_task("llm", SubTask(sub_agent_id="sub-a", task_prompt="t"),
                                      "main", state=state)

        assert res.success and res.content == "done"
        # 进入子图时填充
        assert captured["temp"]["agent_id"] == "sub-a"
        assert captured["temp"]["name"] == "SubA"
        # 退出子图清空
        assert state["temp_sub_config"] is None


class TestRunStreamUnifiedState:

    @pytest.mark.asyncio
    async def test_run_stream_materializes_state(self, monkeypatch):
        from packages.agent.orchestrator.agent_loader import LoadedAgentConfig

        rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
        rt.user_id = 1
        rt.session_id = "s1"
        rt.db = None
        rt.config = SimpleNamespace(recursion_limit=25, timeout_seconds=60)

        class Loader:
            def load_main_agent(self, system_prompt=None, tools=None):
                return LoadedAgentConfig(agent_id="main", name="main",
                                         system_prompt=system_prompt or "你是主Agent",
                                         tools_whitelist=list(tools or []))
            async def list_sub_agents(self, user_id):
                return []
            def resolve_sub_agent_id(self, agent_id, catalog):
                return None
        rt.loader = Loader()

        rt._create_llm = AsyncMock(return_value="llm")
        rt._make_pii_redactor = lambda: None

        async def fake_orchestrate(llm, messages, main_prompt, catalog):
            return OrchestrationPlan(
                need_sub_agents=True, run_mode="serial",
                plan=[SubTask(sub_agent_id="sub-a", task_prompt="do it")],
            )
        rt._orchestrate = fake_orchestrate

        async def fake_exec_sub_task(llm, sub_task, main_prompt, state=None):
            if state is not None:
                state["temp_sub_config"] = {"agent_id": sub_task.sub_agent_id}
            return SubAgentResult(sub_agent_id=sub_task.sub_agent_id, success=True, content="ok")

        rt._exec_sub_task = fake_exec_sub_task

        async def fake_aggregate_stream(llm, results, main_prompt, redactor=None):
            yield "聚合"
        rt._aggregate_stream = fake_aggregate_stream

        async def noop(*a, **k):
            return None
        rt._save_conversation = noop
        rt._save_execution_trace = noop

        monkeypatch.setattr(
            "packages.agent.orchestrator.business_tools.ensure_business_tools",
            lambda *a, **k: None,
        )

        events = [ev async for ev in rt.run_stream("hi", main_prompt="p", session_id="s1")]

        assert any(ev["type"] == "sub_agent" for ev in events)
        assert any(ev["type"] == "token" and ev["content"] == "聚合" for ev in events)

        last = rt._last_orchestrator_state
        # 主常驻配置
        assert last["main_agent_config"]["agent_id"] == "main"
        # 子任务 / 结果 / 终答写回
        assert last["sub_tasks"] == [{"sub_agent_id": "sub-a", "task_prompt": "do it"}]
        assert last["sub_agent_results"][0]["content"] == "ok"
        assert last["final_answer"] == "聚合"
        # 会话信息
        assert last["session_id"] == "s1"
        assert last["messages"] == [{"role": "user", "content": "hi"}]
