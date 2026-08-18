"""tool_event 流事件测试（前端实时工具调用链渲染）。

验证 ToolExecutionManager.execute_tool 在配置 on_tool_event 回调时按约定产出
start/done 事件：工具名、入参（截断）、状态、结果、沙箱产物文件；拒绝路径发
status=denied。默认无回调时不发送、不抛错（既有测试零影响）。
"""
import pytest
from langchain_core.tools import tool

from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk


@pytest.fixture(autouse=True)
def _reset_registries():
    ToolExecutionManager._risks.clear()
    ToolExecutionManager._sandbox_executors.clear()
    yield


class _Recorder:
    """记录 on_tool_event 回调收到的事件。"""

    def __init__(self):
        self.events = []
        self.coro_flag = []

    async def __call__(self, ev):
        self.events.append(ev)


@pytest.mark.asyncio
async def test_read_emits_start_and_done():
    rec = _Recorder()

    @tool
    async def read_tool(q: str = "") -> str:
        """读取类测试工具"""
        return "read:" + q

    read_tool.name = "read_tool"
    ToolExecutionManager.register_tool_risk("read_tool", ToolRisk.READ)

    mgr = ToolExecutionManager(on_tool_event=rec)
    res = await mgr.execute_tool(read_tool, {"q": "hi"})

    assert res == "read:hi"
    types = [(e["data"]["phase"], e["data"]["status"]) for e in rec.events]
    assert types == [("start", "running"), ("done", "success")]
    assert rec.events[0]["type"] == "tool_event"
    assert rec.events[0]["data"]["tool"] == "read_tool"
    assert rec.events[0]["data"]["input"] == {"q": "hi"}


@pytest.mark.asyncio
async def test_denied_emits_done_status_denied():
    rec = _Recorder()

    @tool
    async def a_tool(x: str = "") -> str:
        """白名单外工具"""
        return "a:" + x

    a_tool.name = "a_tool"
    mgr = ToolExecutionManager(
        security_policy={"blocked_tools": ["a_tool"]}, on_tool_event=rec,
    )
    res = await mgr.execute_tool(a_tool, {"x": "hi"})

    assert "[工具被拦截]" in res
    assert len(rec.events) == 1
    d = rec.events[0]["data"]
    assert d["phase"] == "done" and d["status"] == "denied"


@pytest.mark.asyncio
async def test_sandbox_products_surfaced_in_done():
    rec = _Recorder()

    async def _sb(sandbox, tool_input) -> str:
        # 模拟 execute_code 执行器：把生成产物透出到 sandbox 实例
        sandbox._last_products = [{"filename": "out.py", "relative_path": "generated/exec/1/out.py"}]
        sandbox._last_sandbox = "docker-nsjail"
        return "[docker-nsjail] exit=0\nstdout: ok"

    @tool
    async def exec_tool(code: str = "") -> str:
        """执行类测试工具"""
        return "inproc:" + code

    exec_tool.name = "exec_tool"
    ToolExecutionManager.register_tool_risk("exec_tool", ToolRisk.EXECUTE)
    ToolExecutionManager.register_sandbox_executor("exec_tool", _sb)

    mgr = ToolExecutionManager(on_tool_event=rec)
    res = await mgr.execute_tool(exec_tool, {"code": "pass"})

    assert "stdout: ok" in res
    done = rec.events[-1]["data"]
    assert done["status"] == "success"
    assert done["files"] == [{"filename": "out.py", "relative_path": "generated/exec/1/out.py"}]
    assert done["sandbox"] == "docker-nsjail"


@pytest.mark.asyncio
async def test_default_no_callback_is_noop():
    @tool
    async def read_tool(q: str = "") -> str:
        """读取类测试工具"""
        return "read:" + q

    read_tool.name = "read_tool"
    ToolExecutionManager.register_tool_risk("read_tool", ToolRisk.READ)

    mgr = ToolExecutionManager()  # 无 on_tool_event
    res = await mgr.execute_tool(read_tool, {"q": "hi"})
    assert res == "read:hi"  # 不抛错、正常执行


@pytest.mark.asyncio
async def test_input_large_field_truncated():
    rec = _Recorder()

    @tool
    async def read_tool(q: str = "") -> str:
        """读取类测试工具"""
        return "ok"

    read_tool.name = "read_tool"
    ToolExecutionManager.register_tool_risk("read_tool", ToolRisk.READ)

    mgr = ToolExecutionManager(on_tool_event=rec)
    await mgr.execute_tool(read_tool, {"q": "x" * 2000})

    emitted = rec.events[0]["data"]["input"]["q"]
    assert len(emitted) <= 503  # 500 + "..."
    assert emitted.endswith("...")
