"""
Phase 4: 三层铁律把关测试

验证 LangGraph act 节点不裸调用工具，而是经 Harness 工具治理门面执行：
    - 提供 execution_manager 时，高危工具走治理门面（沙箱执行器）
    - 无 execution_manager 时回退 safe_invoke（向后兼容）
"""
import pytest
from langchain_core.tools import tool

from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk
from packages.agent.runtime_engine.tao_graph import create_act_node
from packages.agent.tools.registry import get_tool_registry


@pytest.fixture(autouse=True)
def _reset_global():
    ToolExecutionManager._risks.clear()
    ToolExecutionManager._sandbox_executors.clear()
    reg = get_tool_registry()
    for name in ("ai_exec_tool", "ai_read_tool"):
        try:
            reg.unregister(name)
        except Exception:
            pass
    yield


class TestActNodeGovernance:

    @pytest.mark.asyncio
    async def test_act_node_routes_through_manager(self):
        async def _sb(sandbox, tool_input):
            return "sandbox:" + tool_input["code"]

        @tool
        async def ai_exec_tool(code: str = "") -> str:
            """治理门面测试：高危工具"""
            return "inproc:" + code  # 不应被调用

        ai_exec_tool.name = "ai_exec_tool"
        reg = get_tool_registry()
        reg.register(ai_exec_tool, category="business")
        ToolExecutionManager.register_tool_risk("ai_exec_tool", ToolRisk.EXECUTE)
        ToolExecutionManager.register_sandbox_executor("ai_exec_tool", _sb)

        node = create_act_node([ai_exec_tool], None, ToolExecutionManager())
        out = await node({
            "tool_calls": [{"name": "ai_exec_tool", "args": {"code": "x=1"}}],
            "iteration": 0,
            "messages": [],
        })

        results = out["tool_results"]
        assert results[0]["tool"] == "ai_exec_tool"
        assert results[0]["result"] == "sandbox:x=1"  # 经治理门面走沙箱执行器

    @pytest.mark.asyncio
    async def test_act_node_falls_back_to_safe_invoke_without_manager(self):
        @tool
        async def ai_read_tool(q: str = "") -> str:
            """无 manager 兼容路径"""
            return "read:" + q

        ai_read_tool.name = "ai_read_tool"
        reg = get_tool_registry()
        reg.register(ai_read_tool, category="business")

        node = create_act_node([ai_read_tool], None, None)  # 无 manager
        out = await node({
            "tool_calls": [{"name": "ai_read_tool", "args": {"q": "hi"}}],
            "iteration": 0,
            "messages": [],
        })

        assert out["tool_results"][0]["result"] == "read:hi"
