"""工具执行唯一入口 - Harness 工具治理子系统（设计文档 2.2）

模型禁止直接调用工具，所有工具请求经本门面执行：
    permission_check -> param_clean -> (按风险分级路由进程内/沙箱) -> audit

风险分级（ToolRisk）：
    - READ   读取类（知识库检索、模型/提示词查询等）→ 进程内执行
    - WRITE  写入类（写工作区文件等）→ 走沙箱工作区
    - EXECUTE 执行类（代码/命令/shell 等）→ 走沙箱
    - DENIED 禁止执行 → 直接拒绝

Phase 0 仅建立门面骨架并透传 safe_invoke，不改现有调用路径；
Phase 1 由 execute_tool 按风险分级真正路由到沙箱。
"""
import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ToolRisk(str, Enum):
    """工具风险分级"""
    READ = "read"          # 读取类：安全，进程内执行
    WRITE = "write"        # 写入类：修改文件/数据，走沙箱工作区
    EXECUTE = "execute"    # 执行类：运行代码/命令，走沙箱
    DENIED = "denied"      # 禁止执行


# 默认未知工具视为 READ（最小惊喜，安全兜底在 whitelist 层）
DEFAULT_RISK = ToolRisk.READ


class ToolExecutionManager:
    """Harness 工具执行唯一门面。

    由 OrchestratorRuntime 在装配图时构造并注入 create_act_node，
    使 LangGraph 工具节点只转发请求、在此门面内完成全部治理。
    """

    # 风险注册表（类级，business_tools 可注册；实例级亦可覆盖）
    _risks: Dict[str, ToolRisk] = {}

    # 沙箱执行器注册表：tool_name -> async (sandbox, tool_input) -> str
    # 高危工具将"在沙箱内执行自身能力"的实现注册于此；
    # 工具对象多为 pydantic StructuredTool，不允许附加属性，故用名称键控注册表。
    _sandbox_executors: Dict[str, Callable] = {}

    def __init__(self, db=None, user_id=None, session_id=None, tool_registry=None,
                 sandbox_workdir: Optional[str] = None):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.sandbox_workdir = sandbox_workdir  # 任务级沙箱工作目录（SandboxScope 提供）
        if tool_registry is None:
            from packages.agent.tools.registry import get_tool_registry
            tool_registry = get_tool_registry()
        self._registry = tool_registry

    # ---------------- 风险注册 ----------------
    @classmethod
    def register_tool_risk(cls, tool_name: str, level: ToolRisk) -> None:
        """注册工具风险等级（全局生效）。"""
        cls._risks[tool_name] = level

    @classmethod
    def register_many_risks(cls, mapping: Dict[str, ToolRisk]) -> None:
        for name, level in mapping.items():
            cls._risks[name] = level

    def risk_of(self, tool_name: str) -> ToolRisk:
        return self._risks.get(tool_name, DEFAULT_RISK)

    @classmethod
    def register_sandbox_executor(cls, tool_name: str, fn: Callable) -> None:
        """注册高危工具的沙箱执行器：async (sandbox, tool_input) -> str（幂等）。"""
        cls._sandbox_executors[tool_name] = fn

    # ---------------- 治理钩子（中间件/审计，可被覆盖）----------------
    async def permission_check(self, tool_name: str, tool_params: dict) -> Optional[str]:
        """前置权限/参数校验。返回拒绝原因字符串；None = 放行。"""
        from packages.agent.core.harness.middleware.tool_permission import (
            clean_tool_params,
            run_tool_permission_check,
        )
        denied = run_tool_permission_check(tool_name, tool_params)
        if denied:
            return denied
        return None

    def param_clean(self, tool_name: str, tool_params: dict) -> dict:
        from packages.agent.core.harness.middleware.tool_permission import clean_tool_params
        return clean_tool_params(tool_name, tool_params)

    def audit(self, tool_name: str, tool_params: dict, result: str, sandbox: Optional[str] = None) -> None:
        logger.info(
            "[ToolAudit] tool=%s user=%s session=%s sandbox=%s params=%s",
            tool_name, self.user_id, self.session_id, sandbox or "-", str(tool_params)[:200],
        )

    # ---------------- 沙箱执行（Phase 1 落地）----------------
    async def _execute_in_sandbox(self, tool, tool_input: dict) -> str:
        """把执行/写入类高危工具放到 Harness 沙箱工作区执行。

        执行器按工具名注册于沙箱执行器注册表（async (sandbox, tool_input) -> str）。
        未知/未注册的高危工具（进程内对象无法跨进程序列化）降级到 safe_invoke，不丢功能；
        沙箱缺失或执行失败同样降级并记告警，绝不因沙箱问题中断可用性。
        """
        tool_name = getattr(tool, "name", "?unknown?")
        sandbox_exec = self._sandbox_executors.get(tool_name)
        if sandbox_exec is not None:
            try:
                from packages.agent.harness.sandbox.runtime import SandboxRuntime
                sandbox = SandboxRuntime(
                    db=self.db, user_id=self.user_id or 1, session_id=self.session_id,
                    workdir=self.sandbox_workdir,
                )
                result = await sandbox_exec(sandbox, tool_input)
                if result is not None:
                    return str(result)
            except Exception as e:
                logger.warning(
                    "[ToolExecution] 沙箱执行失败，降级进程内: %s | tool=%s",
                    e, tool_name,
                )
        return await self._registry.safe_invoke(tool, tool_input)

    # ---------------- 唯一执行入口 ----------------
    async def execute_tool(self, tool, tool_input: dict) -> str:
        """工具执行唯一入口：权限/参数校验 → 风险分级路由 → 执行 → 审计。"""
        tool_name = getattr(tool, "name", "?unknown?")
        if not isinstance(tool_input, dict):
            tool_input = {}

        # 1. 前置权限/参数校验
        denied = await self.permission_check(tool_name, tool_input)
        if denied:
            self.audit(tool_name, tool_input, f"DENIED: {denied}")
            return f"[工具被拦截] {tool_name}: {denied}"

        # 2. 参数清洗
        clean_input = self.param_clean(tool_name, tool_input)

        # 3. 按风险分级路由
        risk = self.risk_of(tool_name)
        result = None
        sandbox = None
        if risk in (ToolRisk.EXECUTE, ToolRisk.WRITE):
            sandbox = "harness-sandbox"
            result = await self._execute_in_sandbox(tool, clean_input)
        else:
            result = await self._registry.safe_invoke(tool, clean_input)

        # 4. 审计
        self.audit(tool_name, clean_input, str(result)[:500], sandbox)
        return result
