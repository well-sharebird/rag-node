"""偏差3：Harness 熔断 + 工具门限流/熔断集成单测"""
import pytest
from langchain_core.tools import tool

from packages.agent.core.harness.security.circuit_breaker import CircuitBreaker, CircuitState
from packages.agent.core.harness.tools import ToolExecutionManager
from packages.agent.tools.registry import get_tool_registry


def test_circuit_breaker_state_machine():
    cb = CircuitBreaker(failure_threshold=3, open_timeout=100.0)
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # 未达阈值

    cb.record_failure()
    assert cb.state == CircuitState.OPEN  # 达阈值 → 熔断
    assert cb.is_open is True

    # 半开探测
    cb._opened_at = 0.0  # 模拟超时 → 转 HALF_OPEN
    assert cb.is_open is False
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitState.CLOSED  # 探测成功复位


def test_circuit_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=2, open_timeout=100.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    cb._opened_at = 0.0
    assert cb.is_open is False  # HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN  # 半开失败 → 重新熔断


@pytest.mark.asyncio
async def test_execute_tool_rate_limits():
    @tool
    async def ai_tool(q: str = "") -> str:
        """rate limit 测试工具"""
        return "ok:" + q

    ai_tool.name = "ai_rate_tool"
    reg = get_tool_registry()
    reg.register(ai_tool, category="business")

    # token_bucket capacity=1,refill=0 → 首次放行，后续超限
    mgr = ToolExecutionManager(
        tool_registry=reg, user_id=1, session_id="s",
        rate_limit={"mode": "token_bucket", "capacity": 1, "refill_rate": 0.0},
    )
    r1 = await mgr.execute_tool(ai_tool, {"q": "x"})
    assert r1 == "ok:x"
    r2 = await mgr.execute_tool(ai_tool, {"q": "y"})
    assert "[限流]" in r2


@pytest.mark.asyncio
async def test_execute_tool_no_config_passes_through():
    @tool
    async def ai_tool(q: str = "") -> str:
        """无配置透传测试工具"""
        return "ok:" + q

    ai_tool.name = "ai_config_free_tool"
    reg = get_tool_registry()
    reg.register(ai_tool, category="business")

    mgr = ToolExecutionManager(tool_registry=reg, user_id=1, session_id="s")
    # 未配置限流/熔断 → 行为不变（放行）
    assert await mgr.execute_tool(ai_tool, {"q": "x"}) == "ok:x"
    assert await mgr.execute_tool(ai_tool, {"q": "y"}) == "ok:y"


@pytest.mark.asyncio
async def test_execute_tool_circuit_opens_after_failures():
    @tool
    async def failing_tool(q: str = "") -> str:
        """熔断测试工具：总是失败"""
        raise RuntimeError("boom")

    failing_tool.name = "ai_circuit_tool"
    reg = get_tool_registry()
    reg.register(failing_tool, category="business")

    mgr = ToolExecutionManager(
        tool_registry=reg, user_id=1, session_id="s",
        circuit={"failure_threshold": 2, "open_timeout": 100.0},
    )
    # safe_invoke 吞异常，返回 `[工具执行失败]` 标记 → 熔断失败计数递增
    r1 = await mgr.execute_tool(failing_tool, {})
    assert "[工具执行失败]" in r1
    r2 = await mgr.execute_tool(failing_tool, {})
    assert "[工具执行失败]" in r2
    # 两次失败达阈值 → 熔断 OPEN，第三次不再执行而是降级拒绝
    r3 = await mgr.execute_tool(failing_tool, {})
    assert "[熔断]" in r3
