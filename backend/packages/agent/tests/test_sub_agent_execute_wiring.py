"""
Phase 4 #2: 子 Agent 统一经运行时 execute 接线测试

验证 _run_sub_agent_graph 改走 self.execute 后仍正确保留：
    - 结果内置审批（state.__interrupt__ → approvals）
    - 审批异常（ExecutionResult.error 携带 GraphInterrupt 类异常 → approvals）
    - 超时（metadata.timeout → 超时错误）
    - 通用失败（error_message → 错误结果）
"""
import pytest

from packages.agent.orchestrator.graph import OrchestratorRuntime
from packages.agent.runtime_engine.state import ExecutionResult


class _Cfg:
    agent_id = "sub-a"
    max_step = 3


def _runtime(exec_result):
    rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
    rt.config = type("C", (), {"timeout_seconds": 60})()
    rt.user_id = 1

    async def fake_execute(graph, state, thread_id, **kw):
        return exec_result

    rt.execute = fake_execute
    rt._build_agent_graph = lambda **kw: object()
    return rt


@pytest.mark.asyncio
async def test_success_returns_content():
    rt = _runtime(ExecutionResult.ok({"messages": []}, 10))
    res = await rt._run_sub_agent_graph(None, [], "sys", {}, _Cfg(), "task")
    assert res.success is True
    assert res.content == ""


@pytest.mark.asyncio
async def test_approval_inside_result_state():
    state = {"messages": [], "__interrupt__": {
        "type": "approval_required",
        "pending": [{"tool": "save_workspace_file", "args": {}, "request_id": "r1"}],
    }}
    rt = _runtime(ExecutionResult.ok(state, 10))
    res = await rt._run_sub_agent_graph(None, [], "sys", {}, _Cfg(), "task")
    assert res.success is True
    assert len(res.approvals) == 1
    assert res.approvals[0]["tool"] == "save_workspace_file"


@pytest.mark.asyncio
async def test_approval_from_error_exception():
    class _Interrupt(Exception):
        interrupts = {"pending": [{"tool": "shell_run", "args": {}, "request_id": "r2"}]}

    rt = _runtime(ExecutionResult.error("interrupted", 10, error=_Interrupt("int")))
    res = await rt._run_sub_agent_graph(None, [], "sys", {}, _Cfg(), "task")
    assert res.success is True
    assert len(res.approvals) == 1
    assert res.approvals[0]["tool"] == "shell_run"


@pytest.mark.asyncio
async def test_timeout_reported():
    rt = _runtime(ExecutionResult.error("执行超时（>60s）", 10, metadata={"timeout": True}))
    res = await rt._run_sub_agent_graph(None, [], "sys", {}, _Cfg(), "task")
    assert res.success is False
    assert "超时" in res.error


@pytest.mark.asyncio
async def test_generic_error_reported():
    rt = _runtime(ExecutionResult.error("boom", 10))
    res = await rt._run_sub_agent_graph(None, [], "sys", {}, _Cfg(), "task")
    assert res.success is False
    assert res.error == "boom"
