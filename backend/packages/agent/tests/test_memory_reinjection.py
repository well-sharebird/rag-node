"""
Phase 4: 会话记忆回灌测试

验证 _load_conversation_history：
    - 无 session_id → 空
    - DB 异常 → 退化空（不中断）
    - 命中会话 → 返回按索引排序的用户/助手消息序列（旧→新）
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from packages.agent.orchestrator.graph import OrchestratorRuntime


def _runtime(db):
    rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
    rt.db = db
    return rt


class TestHistoryReinjection:

    @pytest.mark.asyncio
    async def test_empty_without_session(self):
        rt = _runtime(None)
        assert await rt._load_conversation_history(1, None) == []

    @pytest.mark.asyncio
    async def test_empty_on_db_error(self):
        rt = _runtime("not-a-db")  # 触发异常 → 捕获退化空
        assert await rt._load_conversation_history(1, "s") == []

    @pytest.mark.asyncio
    async def test_returns_ordered_messages(self):
        class FakeMsg:
            def __init__(self, role, content, index):
                self.role, self.content, self.message_index = role, content, index

        class FakeConv:
            id = "c1"
            metadata_json = '{"session_id":"s1"}'

        msgs = [
            FakeMsg("user", "hi", 1),
            FakeMsg("assistant", "hello", 2),
            FakeMsg("user", "what next", 3),
        ]

        class FakeScalars:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        class FakeResult:
            def __init__(self, items):
                self._items = items

            def scalars(self):
                return FakeScalars(self._items)

        calls = iter([FakeResult([FakeConv()]), FakeResult(msgs)])

        class FakeDB:
            async def execute(self, stmt):
                return next(calls)

        rt = _runtime(FakeDB())
        out = await rt._load_conversation_history(1, "s1", limit=10)

        assert isinstance(out[0], HumanMessage) and out[0].content == "hi"
        assert isinstance(out[1], AIMessage) and out[1].content == "hello"
        assert isinstance(out[2], HumanMessage) and out[2].content == "what next"

    @pytest.mark.asyncio
    async def test_does_not_match_wrong_session(self):
        class FakeConv:
            id = "c1"
            metadata_json = '{"session_id":"OTHER"}'

        class FakeScalars:
            def all(self):
                return [FakeConv()]

        class FakeResult:
            def scalars(self):
                return FakeScalars()

        class FakeDB:
            async def execute(self, stmt):
                return FakeResult()

        rt = _runtime(FakeDB())
        assert await rt._load_conversation_history(1, "s1") == []
