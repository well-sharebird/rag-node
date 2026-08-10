"""内置 Hook — 迁移自 plan_middleware.py 和废弃的中间件"""
from packages.agent.hooks.registry import hook, HookPoint
import logging
import re

logger = logging.getLogger(__name__)


@hook(HookPoint.BEFORE_AGENT, priority=0)
async def init_context(state: dict) -> dict:
    """初始化执行上下文"""
    if "context" not in state:
        state["context"] = {}
    if "context" not in state:
        state["context"]["started_at"] = True
    return state


@hook(HookPoint.AFTER_AGENT, priority=0)
async def extract_todos(state: dict) -> dict:
    """从输出中提取 [TASK] 标记（迁移自 PlanMiddleware）"""
    messages = state.get("messages", [])
    if not messages:
        return state

    # 从最后一条消息中提取
    last_msg = messages[-1]
    content = getattr(last_msg, "content", str(last_msg)) if hasattr(last_msg, "content") else str(last_msg)

    tasks = re.findall(r"\[TASK\](.+?)(?:\n|$)", content)
    if tasks:
        if "context" not in state:
            state["context"] = {}
        state["context"]["extracted_tasks"] = tasks
        logger.info(f"[Hook] Extracted {len(tasks)} tasks")

    return state


@hook(HookPoint.BEFORE_ACT, priority=10)
async def log_tool_call(state: dict) -> dict:
    """记录工具调用（迁移自 LoggingMiddleware）"""
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        tool_names = [tc.get("name", "unknown") for tc in tool_calls]
        logger.info(f"[Hook] Tool calls: {tool_names}")
    return state


@hook(HookPoint.AFTER_ACT, priority=0)
async def log_tool_result(state: dict) -> dict:
    """记录工具执行结果"""
    tool_results = state.get("tool_results", [])
    if tool_results:
        logger.info(f"[Hook] Tool results: {len(tool_results)} items")
    return state
