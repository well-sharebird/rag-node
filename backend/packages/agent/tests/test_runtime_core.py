"""原子运行时组件单测：retry / context / state"""
import asyncio
import pytest

from packages.agent.core.harness.security.retry import RetryPolicy, with_retry
from packages.agent.core.harness.context import ContextCompressor
from packages.agent.runtime_engine.state import append_lists, extract_tasks, update_todos_from_message


# ============================================================
# retry
# ============================================================

class TestRetry:
    async def test_retries_until_success(self):
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return "ok"

        result = await with_retry(flaky, RetryPolicy(max_retries=3, delay_seconds=0))
        assert result == "ok"
        assert calls["n"] == 3

    async def test_max_retries_exhausted_raises(self):
        async def always_fail():
            raise ValueError("persistent")

        with pytest.raises(ValueError):
            await with_retry(always_fail, RetryPolicy(max_retries=2, delay_seconds=0))

    async def test_non_retryable_exception_no_retry(self):
        calls = {"n": 0}

        async def fails_once():
            calls["n"] += 1
            raise KeyError("nope")

        # 只重试 ValueError，KeyError 应直接冒泡且不重试
        with pytest.raises(KeyError):
            await with_retry(
                fails_once,
                RetryPolicy(max_retries=3, retryable_exceptions=(ValueError,), delay_seconds=0),
            )
        assert calls["n"] == 1

    async def test_custom_should_retry(self):
        calls = {"n": 0}

        async def fails_with_500_then_ok():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("500")
            return "done"

        policy = RetryPolicy(
            max_retries=2,
            delay_seconds=0,
            should_retry=lambda exc: "500" in str(exc),
        )
        assert await with_retry(fails_with_500_then_ok, policy) == "done"


# ============================================================
# context
# ============================================================

class TestContextCompressor:
    def test_should_compress_under_budget(self):
        from langchain_core.messages import HumanMessage
        small = [HumanMessage(content="hi")]
        # 预算远大于消息，不应压缩
        c = ContextCompressor(max_tokens=4096, reserve_tokens=512)
        assert c.should_compress(small) is False

    def test_compress_over_budget_keeps_system(self):
        from langchain_core.messages import SystemMessage, HumanMessage
        big = [SystemMessage(content="你是助手约束")] + [
            HumanMessage(content="这是一段很长的历史消息内容" * 50) for _ in range(20)
        ]
        c = ContextCompressor(max_tokens=64, reserve_tokens=0)
        assert c.should_compress(big) is True
        out = c.compress(big)
        # system 消息必须保留
        assert isinstance(out[0], SystemMessage)
        # 压缩后不应超预算（近似）且有削减
        assert len(out) < len(big)

    def test_estimate(self):
        from langchain_core.messages import HumanMessage
        c = ContextCompressor(max_tokens=1000, reserve_tokens=0)
        assert c.estimate([HumanMessage(content="测试内容")]) > 0


# ============================================================
# state
# ============================================================

class TestState:
    def test_append_lists_dedup(self):
        merged = append_lists([{"description": "a"}], [{"description": "a"}, {"description": "b"}])
        assert merged == [{"description": "a"}, {"description": "b"}]

    def test_extract_tasks(self):
        tasks = extract_tasks("[TASK] 写文档\n- [ ] 任务A\n- [x] 任务B")
        assert "写文档" in tasks
        assert "任务A" in tasks
        assert "任务B" in tasks

    def test_update_todos_from_message_merges(self):
        state = {"todos": [{"description": "a", "status": "pending"}]}
        update = update_todos_from_message(state, "[TASK] a\n[TASK] b")
        todos = update["todos"]
        descs = [t["description"] for t in todos]
        assert descs == ["a", "b"]  # 不重复追加 a

    def test_update_todos_no_task_returns_empty(self):
        assert update_todos_from_message({}, "没有任务标记") == {}
