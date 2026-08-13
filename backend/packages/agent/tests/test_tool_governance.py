"""
Phase 1: Harness 工具治理门面测试

验证 ToolExecutionManager 按风险分级路由：
    - READ       → 进程内 safe_invoke
    - EXECUTE    → 沙箱执行（sandbox_execute 扩展点）
    - 默认未知    → READ（最小惊喜）
风险注册幂等；权限校验纯函数生效。
"""
import pytest
from langchain_core.tools import tool

from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk


@pytest.fixture(autouse=True)
def _reset_registries():
    ToolExecutionManager._risks.clear()
    ToolExecutionManager._sandbox_executors.clear()
    yield


class TestExecutionManagerRouting:

    @pytest.mark.asyncio
    async def test_read_routes_to_safe_invoke(self):
        called = {}

        @tool
        async def read_tool(q: str = "") -> str:
            """读取类测试工具"""
            called["invoked"] = q
            return f"read:{q}"

        read_tool.name = "read_tool"
        ToolExecutionManager.register_tool_risk("read_tool", ToolRisk.READ)

        mgr = ToolExecutionManager()
        res = await mgr.execute_tool(read_tool, {"q": "hi"})

        assert res == "read:hi"
        assert called.get("invoked") == "hi"

    @pytest.mark.asyncio
    async def test_execute_routes_to_sandbox(self):
        async def _sb(sandbox, tool_input):
            return "sandbox:" + tool_input["code"]

        @tool
        async def exec_tool(code: str = "") -> str:
            """执行类测试工具"""
            return "inproc:" + code  # 不应被调用

        exec_tool.name = "exec_tool"
        ToolExecutionManager.register_tool_risk("exec_tool", ToolRisk.EXECUTE)
        ToolExecutionManager.register_sandbox_executor("exec_tool", _sb)

        mgr = ToolExecutionManager()
        res = await mgr.execute_tool(exec_tool, {"code": "x=1"})

        assert res == "sandbox:x=1"  # EXECUTE → _execute_in_sandbox → 沙箱执行器

    @pytest.mark.asyncio
    async def test_execute_sandbox_unavailable_falls_back_to_safe_invoke(self):
        # 无 sandbox_execute 的高危工具：沙箱缺失 → 降级 safe_invoke，不丢功能
        @tool
        async def risky_tool(code: str = "") -> str:
            """无沙箱扩展的高危测试工具"""
            return "safe:" + code

        risky_tool.name = "risky_tool"
        ToolExecutionManager.register_tool_risk("risky_tool", ToolRisk.EXECUTE)

        mgr = ToolExecutionManager()
        res = await mgr.execute_tool(risky_tool, {"code": "z"})

        assert res == "safe:z"

    def test_risk_classification(self):
        mgr = ToolExecutionManager()
        ToolExecutionManager.register_many_risks({
            "execute_code": ToolRisk.EXECUTE,
            "save_workspace_file": ToolRisk.WRITE,
            "list_knowledge_bases": ToolRisk.READ,
        })
        assert mgr.risk_of("execute_code") == ToolRisk.EXECUTE
        assert mgr.risk_of("save_workspace_file") == ToolRisk.WRITE
        assert mgr.risk_of("list_knowledge_bases") == ToolRisk.READ
        assert mgr.risk_of("unknown_tool") == ToolRisk.READ  # 默认兜底

    def test_permission_check_pure_function(self):
        from packages.agent.core.harness.middleware import run_tool_permission_check

        assert run_tool_permission_check("kill", {}, {"blocked_tools": ["kill"]}) is not None
        assert run_tool_permission_check("ls", {}, {"blocked_tools": ["kill"]}) is None
        assert run_tool_permission_check(
            "search", {}, {"allowed_tools": ["search"]}
        ) is None
        assert run_tool_permission_check(
            "x", {}, {"allowed_tools": ["search"]}
        ) is not None
