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
                 sandbox_workdir: Optional[str] = None, security_policy: Optional[dict] = None,
                 rate_limit: Optional[dict] = None, circuit: Optional[dict] = None,
                 on_tool_event: Optional[Callable] = None):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.sandbox_workdir = sandbox_workdir  # 任务级沙箱工作目录（SandboxScope 提供）
        # 安全策略（blocked_tools/allowed_tools，与 AgentConfig.security_policy 对齐）：
        # 工具级护栏（纵深防御）——即使 LLM 尝试白名单外工具，也在此门强制拒绝。
        self._policy = security_policy or {}
        # 流式工具事件回调：async (event: dict) -> None（前端实时工具调用链）；None 则不发送。
        self._on_tool_event = on_tool_event

        # 限流配置（可选）：{"mode": "token_bucket"|"sliding_window", ...params, "key_by": "user"|"tool"}
        self._rate_limit_cfg = rate_limit or {}
        # 熔断配置（可选）：{"failure_threshold": N, "open_timeout": sec, "key_by": "tool"}
        self._circuit_cfg = circuit or {}
        # （懒构造）按 key 缓存限流器/熔断器实例
        self._rate_limiters: Dict[str, Any] = {}
        self._circuit_breakers: Dict[str, Any] = {}

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
        denied = run_tool_permission_check(tool_name, tool_params, self._policy)
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

    # ---------------- 流式工具事件（前端实时工具调用链渲染）----------------
    @staticmethod
    def _truncate_input(tool_input: dict) -> dict:
        """截断入参字符串字段，避免 code/content 等大字段刷爆事件流。"""
        out: Dict[str, Any] = {}
        for k, v in (tool_input or {}).items():
            if isinstance(v, str) and len(v) > 500:
                out[k] = v[:500] + "..."
            else:
                out[k] = v
        return out

    async def _emit_tool_event(self, phase: str, tool: str, tool_input: dict, *,
                               status: Optional[str] = None, result: Optional[str] = None,
                               files: Optional[list] = None, sandbox: Optional[str] = None) -> None:
        """向 on_tool_event 回调发送一次工具事件；未配置回调则直接返回（零开销）。"""
        if self._on_tool_event is None:
            return
        data: Dict[str, Any] = {
            "phase": phase,
            "tool": tool,
            "input": self._truncate_input(tool_input),
        }
        if status is not None:
            data["status"] = status
        if result is not None:
            data["result"] = str(result)[:2000]
        if files is not None:
            data["files"] = files
        if sandbox is not None:
            data["sandbox"] = sandbox
        try:
            from packages.agent.schemas.stream import ev_tool
            await self._on_tool_event(ev_tool(data))
        except Exception as e:
            logger.warning("[ToolExecution] tool_event 发送失败: %s", e)

    # ---------------- 沙箱执行（Phase 1 落地）----------------
    async def _execute_in_sandbox(self, tool, tool_input: dict) -> tuple[str, list, str]:
        """把执行/写入类高危工具放到 Harness 沙箱工作区执行。

        执行器按工具名注册于沙箱执行器注册表（async (sandbox, tool_input) -> str）。
        未知/未注册的高危工具（进程内对象无法跨进程序列化）降级到 safe_invoke，不丢功能；
        沙箱缺失或执行失败同样降级并记告警，绝不因沙箱问题中断可用性。

        返回 (result_str, products, sandbox_label)：products 由执行器经 `sandbox._last_products`
        透出（如 execute_code 的生成产物），供 tool_event 前端渲染；sandbox_label 为执行后端标识。
        """
        tool_name = getattr(tool, "name", "?unknown?")
        sandbox_exec = self._sandbox_executors.get(tool_name)
        if sandbox_exec is not None:
            try:
                from packages.agent.core.harness.sandbox.runtime import SandboxRuntime
                sandbox = SandboxRuntime(
                    db=self.db, user_id=self.user_id or 1, session_id=self.session_id,
                    workdir=self.sandbox_workdir,
                )
                result = await sandbox_exec(sandbox, tool_input)
                if result is not None:
                    products = list(getattr(sandbox, "_last_products", None) or [])
                    label = getattr(sandbox, "_last_sandbox", "") or ""
                    return str(result), products, label
            except Exception as e:
                logger.warning(
                    "[ToolExecution] 沙箱执行失败，降级进程内: %s | tool=%s",
                    e, tool_name,
                )
        result = await self._registry.safe_invoke(tool, tool_input)
        return str(result), [], ""

    # ---------------- 限流 / 熔断 ----------------
    def _limit_key(self, tool_name: str) -> str:
        if self._rate_limit_cfg.get("key_by") == "tool":
            return f"tool:{tool_name}"
        return f"user:{self.user_id or 0}"

    def _circuit_key(self, tool_name: str) -> str:
        if self._circuit_cfg.get("key_by") == "user":
            return f"user:{self.user_id or 0}"
        return f"tool:{tool_name}"

    def _rate_limited(self, tool_name: str) -> bool:
        mode = self._rate_limit_cfg.get("mode")
        if not mode:
            return False
        from packages.agent.core.harness.security.rate_limit import make_rate_limiter
        key = self._limit_key(tool_name)
        limiter = self._rate_limiters.get(key)
        if limiter is None:
            params = {k: v for k, v in self._rate_limit_cfg.items() if k not in ("mode", "key_by")}
            limiter = make_rate_limiter(mode, **params)
            self._rate_limiters[key] = limiter
        if hasattr(limiter, "consume"):
            return not limiter.consume()
        return not limiter.allow()

    def _get_circuit_breaker(self, tool_name: str):
        key = self._circuit_key(tool_name)
        cb = self._circuit_breakers.get(key)
        if cb is None:
            from packages.agent.core.harness.security.circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(
                failure_threshold=self._circuit_cfg.get("failure_threshold", 5),
                open_timeout=self._circuit_cfg.get("open_timeout", 30.0),
            )
            self._circuit_breakers[key] = cb
        return cb

    def _circuit_open(self, tool_name: str) -> bool:
        if not self._circuit_cfg:
            return False
        return self._get_circuit_breaker(tool_name).is_open

    def _record_success(self, tool_name: str) -> None:
        if not self._circuit_cfg:
            return
        self._get_circuit_breaker(tool_name).record_success()

    def _record_failure(self, tool_name: str) -> None:
        if not self._circuit_cfg:
            return
        self._get_circuit_breaker(tool_name).record_failure()

    # ---------------- 唯一执行入口 ----------------
    async def execute_tool(self, tool, tool_input: dict) -> str:
        """工具执行唯一入口：权限/参数校验 → 限流 → 熔断 → 风险分级路由 → 执行 → 审计。"""
        tool_name = getattr(tool, "name", "?unknown?")
        if not isinstance(tool_input, dict):
            tool_input = {}

        # 1. 前置权限/参数校验
        denied = await self.permission_check(tool_name, tool_input)
        if denied:
            self.audit(tool_name, tool_input, f"DENIED: {denied}")
            await self._emit_tool_event("done", tool_name, tool_input, status="denied",
                                        result=f"[工具被拦截] {tool_name}: {denied}")
            return f"[工具被拦截] {tool_name}: {denied}"

        # 1.5 限流：超限直接拒绝（未配置时放行）
        if self._rate_limited(tool_name):
            self.audit(tool_name, tool_input, "RATE_LIMITED")
            await self._emit_tool_event("done", tool_name, tool_input, status="limited",
                                        result=f"[限流] {tool_name}: 请求过于频繁，请稍后再试")
            return f"[限流] {tool_name}: 请求过于频繁，请稍后再试"

        # 1.6 熔断：OPEN 时降级拒绝（保护下游）
        if self._circuit_open(tool_name):
            self.audit(tool_name, tool_input, "CIRCUIT_OPEN")
            await self._emit_tool_event("done", tool_name, tool_input, status="circuit",
                                        result=f"[熔断] {tool_name}: 服务暂不可用，请稍后再试")
            return f"[熔断] {tool_name}: 服务暂不可用，请稍后再试"

        # 2. 参数清洗
        clean_input = self.param_clean(tool_name, tool_input)

        # 2.5 工具开始（前端实时渲染运行中状态）
        await self._emit_tool_event("start", tool_name, clean_input, status="running")

        # 3. 按风险分级路由（执行异常计入熔断计数，仍向上抛出）
        risk = self.risk_of(tool_name)
        result = None
        sandbox = None
        products: list = []
        try:
            if risk in (ToolRisk.EXECUTE, ToolRisk.WRITE):
                sandbox = "harness-sandbox"
                result, products, sb_label = await self._execute_in_sandbox(tool, clean_input)
                if sb_label:
                    sandbox = sb_label
            else:
                result = await self._registry.safe_invoke(tool, clean_input)
        except Exception:
            self._record_failure(tool_name)
            await self._emit_tool_event("done", tool_name, clean_input, status="error",
                                        result="工具执行异常", sandbox=sandbox)
            raise

        # 熔断成败判定：safe_invoke 已吞异常并以 `[工具执行失败]` 标记返回
        if isinstance(result, str) and result.startswith("[工具执行失败]"):
            self._record_failure(tool_name)
            status = "error"
        else:
            self._record_success(tool_name)
            status = "success"

        await self._emit_tool_event("done", tool_name, clean_input, status=status,
                                    result=str(result)[:2000], files=products or None,
                                    sandbox=sandbox)

        # 4. 审计
        self.audit(tool_name, clean_input, str(result)[:500], sandbox)
        return result
