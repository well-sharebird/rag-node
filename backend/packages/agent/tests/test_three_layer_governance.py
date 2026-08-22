"""
Phase 4: 三层铁律把关测试

验证中间件架构中的工具治理机制：
    - 高危工具通过中间件进行沙箱执行
    - 权限检查在中间件层完成
"""
import pytest
from langchain_core.tools import tool

from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk
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


class TestToolGovernance:

    @pytest.mark.asyncio
    async def test_tool_risk_classification(self):
        """测试工具风险分类"""
        @tool
        async def ai_exec_tool(code: str = "") -> str:
            """高危工具测试"""
            return "executed:" + code

        ai_exec_tool.name = "ai_exec_tool"
        reg = get_tool_registry()
        reg.register(ai_exec_tool, category="business")
        ToolExecutionManager.register_tool_risk("ai_exec_tool", ToolRisk.EXECUTE)

        # 验证风险分类
        assert ToolExecutionManager.get_tool_risk("ai_exec_tool") == ToolRisk.EXECUTE
        print("✅ Tool risk classification test passed")
