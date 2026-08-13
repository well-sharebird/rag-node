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


class TestToolLevelGuardrailPolicy:
    """#1：execute_tool 门内强制工具级白名单（纵深防御，非仅观测）。"""

    @pytest.mark.asyncio
    async def test_whitelist_blocks_out_of_whitelist_tool(self):
        @tool
        async def evil_tool(x: str = "") -> str:
            """不该被允许执行"""
            return "executed"

        evil_tool.name = "evil_tool"
        mgr = ToolExecutionManager(
            security_policy={"allowed_tools": ["read_tool", "search"]},
        )
        res = await mgr.execute_tool(evil_tool, {"x": "hi"})
        assert res.startswith("[工具被拦截]")
        assert "不在授权白名单" in res

    @pytest.mark.asyncio
    async def test_blocked_tool_rejected_inside_gate(self):
        @tool
        async def a_tool(x: str = "") -> str:
            """被阻断的工具"""
            return "no"

        a_tool.name = "a_tool"
        mgr = ToolExecutionManager(security_policy={"blocked_tools": ["a_tool"]})
        res = await mgr.execute_tool(a_tool, {"x": "hi"})
        assert res.startswith("[工具被拦截]")
        assert "阻断名单" in res

    @pytest.mark.asyncio
    async def test_no_policy_allows(self):
        """无策略（None）时行为不变——放行而非误伤。"""
        @tool
        async def ok_tool(x: str = "") -> str:
            """普通读取工具"""
            return "ok"

        ok_tool.name = "ok_tool"
        mgr = ToolExecutionManager()  # 无 policy
        res = await mgr.execute_tool(ok_tool, {"x": "hi"})
        assert res == "ok"
