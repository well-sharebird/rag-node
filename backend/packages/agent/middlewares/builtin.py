"""内置中间件 - 基于 LangChain AgentMiddleware

管控逻辑（日志、上下文、审计、安全事件）统一为官方中间件。
"""
import logging
import time
from typing import Any, Dict, List, Optional

from langchain.agents.middleware import AgentMiddleware, Runtime

logger = logging.getLogger(__name__)


class ContextInitMiddleware(AgentMiddleware):
    """初始化 State.context（迁移自旧 init_context hook）"""

    async def abefore_agent(self, state: dict, runtime: Runtime) -> Optional[Dict[str, Any]]:
        if "context" not in state or not isinstance(state.get("context"), dict):
            state["context"] = {}
        state["context"].setdefault("started_at", True)
        return {"context": state["context"]}


class ToolLoggingMiddleware(AgentMiddleware):
    """记录工具调用与结果（迁移自旧 log_tool_call / log_tool_result hooks）"""

    def _tool_calls_names(self, state: dict) -> list:
        calls = state.get("tool_calls") or []
        return [tc.get("name", "unknown") if isinstance(tc, dict) else str(tc) for tc in calls]

    def _tool_results_count(self, state: dict) -> int:
        return len(state.get("tool_results") or [])

    async def abefore_model(self, state: dict, runtime: Runtime) -> Optional[Dict[str, Any]]:
        calls = self._tool_calls_names(state)
        if calls:
            logger.info("[Middleware] 待执行工具: %s", calls)
        return None

    async def aafter_model(self, state: dict, runtime: Runtime) -> Optional[Dict[str, Any]]:
        n = self._tool_results_count(state)
        if n:
            logger.info("[Middleware] 工具结果: %d 项", n)
        return None


class AuditLoggerMiddleware(AgentMiddleware):
    """审计中间件：记录 Agent 生命周期、模型调用与耗时（观测面）。"""

    def __init__(self, sink: Any = None, **kwargs):
        super().__init__()
        self._sink = sink  # 可选：结构化审计写入目标（默认仅 logger）
        self._timers: Dict[str, float] = {}
        self._llm_calls = 0
        self._tool_calls = 0

    def _run_id(self, state: dict) -> str:
        md = state.get("metadata") or {}
        return str(md.get("run_id") or state.get("context", {}).get("run_id") or "unknown")

    async def abefore_agent(self, state, runtime) -> None:
        self._timers["agent"] = time.time()
        logger.info("[Audit] agent 开始 | run=%s", self._run_id(state))

    async def aafter_agent(self, state, runtime) -> None:
        t = self._timers.pop("agent", None)
        elapsed = int((time.time() - t) * 1000) if t else 0
        record = {
            "run_id": self._run_id(state),
            "action": "agent_end",
            "latency_ms": elapsed,
            "llm_calls": self._llm_calls,
            "tool_calls": self._tool_calls,
        }
        logger.info("[Audit] agent 结束 | %s", record)
        if self._sink is not None:
            try:
                await self._sink(record) if hasattr(self._sink, "__await__") else None
            except Exception:
                pass

    async def abefore_model(self, state, runtime) -> None:
        self._timers["model"] = time.time()

    async def aafter_model(self, state, runtime) -> None:
        t = self._timers.pop("model", None)
        self._llm_calls += 1
        calls = [tc.get("name", "?") if isinstance(tc, dict) else "?" for tc in (state.get("tool_calls") or [])]
        if calls:
            self._tool_calls += 1
        logger.info(
            "[Audit] 模型调用 #%d | run=%s latency=%dms tools=%s",
            self._llm_calls, self._run_id(state),
            int((time.time() - t) * 1000) if t else 0, calls,
        )


class SecurityGuardMiddleware(AgentMiddleware):
    """安全中间件：检测工具调用中的 blocked/denied 事件（安全审计事件）。

    注意：权限的强制执行由 permission_check 图节点保证；
    此中间件负责安全事件的记录与观测（符合“节点强制 / 中间件观测”分层）。
    """

    def __init__(self, policy: Optional[dict] = None, **kwargs):
        super().__init__()
        self.policy = policy or {}
        self._blocked = set(self.policy.get("blocked_tools") or [])
        self._allowed = set(self.policy.get("allowed_tools") or [])

    def _scan(self, state: dict) -> List[str]:
        events = []
        for tc in state.get("tool_calls") or []:
            name = tc.get("name") if isinstance(tc, dict) else None
            if not name:
                continue
            if name in self._blocked:
                events.append(f"blocked:{name}")
            elif self._allowed and name not in self._allowed:
                events.append(f"denied(not-in-whitelist):{name}")
        return events

    async def aafter_model(self, state, runtime) -> None:
        events = self._scan(state)
        for ev in events:
            logger.warning("[Security] %s | run=%s", ev, (state.get("metadata") or {}).get("run_id", "unknown"))
