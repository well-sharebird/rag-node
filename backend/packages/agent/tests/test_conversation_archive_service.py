"""ConversationArchiveService 核心路径测试。

conversation_archive_service.py（~760 行）此前 0 测试。此处用假 DB 覆盖：
- 纯摘要/预览/关键词逻辑
- 温层归档：gzip 压缩往返 + 源消息清理 + 统计字段
- 冷/温恢复：解压回写 AgentMemory + 标记 is_restored
不依赖真实 PostgreSQL / MinIO。
"""
import gzip
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sqlalchemy.sql.elements import ClauseElement

import app.models  # noqa: F401  （满足 SQLAlchemy mapper 顺序）

from packages.agent.services.conversation_archive_service import ConversationArchiveService


def _config(**over):
    cfg = {
        "compression_enabled": True,
        "compression_level": 6,
        "minio_prefix": "archives",
        "minio_bucket": "rag-archive",
        "cold_tier_days": 365,
        "hot_tier_days": 7,
        "warm_tier_days": 30,
        "archive_batch_size": 100,
        "min_message_count": 2,
    }
    cfg.update(over)
    return SimpleNamespace(**cfg)


class _FakeDB:
    """捕获 add / commit / execute；对 select 从 results 队列弹结果，delete 记录 last_delete。"""

    def __init__(self, results=None):
        self.added = []
        self.commits = 0
        self.results = list(results or [])
        self.last_delete = None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return obj

    async def execute(self, stmt):
        if isinstance(stmt, ClauseElement) and stmt.__class__.__name__ == "Delete":
            self.last_delete = stmt
            return SimpleNamespace(all=lambda: [], scalar=lambda: None)
        return self.results.pop(0) if self.results else None


def _messages():
    return [
        {"role": "user", "content": "你好，帮我总结项目"},
        {"role": "assistant", "content": "项目总结如下"},
        {"role": "user", "content": "还有别的么"},
    ]


# ---------------- 纯逻辑 ----------------
def test_generate_summary_uses_first_user_message():
    assert ConversationArchiveService._generate_summary(None, _messages()) == "用户询问：你好，帮我总结项目..."
    assert ConversationArchiveService._generate_summary(None, []) == ""
    assert ConversationArchiveService._generate_summary(None, [{"role": "assistant", "content": "x"}]) == ""


def test_last_message_preview():
    assert ConversationArchiveService._get_last_message_preview(None, _messages()) == "还有别的么"
    assert ConversationArchiveService._get_last_message_preview(None, []) == ""
    long = [{"role": "user", "content": "长" * 200}]
    assert len(ConversationArchiveService._get_last_message_preview(None, long)) == 100


def test_extract_keywords_default_empty():
    assert ConversationArchiveService._extract_keywords(None, _messages()) == []


# ---------------- 温层归档 ----------------
@pytest.mark.asyncio
async def test_archive_to_warm_compresses_and_persists():
    db = _FakeDB()
    svc = ConversationArchiveService(db)
    svc._get_config = AsyncMock(return_value=_config())
    svc._get_agent_name = AsyncMock(return_value="AgentA")

    msgs = _messages()
    await svc._archive_to_warm(
        user_id=1, thread_id="t1", agent_id="a1", messages=msgs,
        date_range_start=datetime(2026, 1, 1), date_range_end=datetime(2026, 1, 2),
    )

    assert db.commits == 1
    a = db.added[0]
    assert a.archive_tier == "warm"
    assert a.message_count == 3
    assert a.agent_name == "AgentA"
    assert a.thread_id == "t1"
    # gzip 往返无损
    decoded = gzip.decompress(a.compressed_content).decode("utf-8")
    assert [json.loads(x) for x in decoded.split("\n") if x.strip()] == msgs
    assert a.archive_size_bytes == len(a.compressed_content)
    assert a.summary == "用户询问：你好，帮我总结项目..."
    assert a.last_message_preview == "还有别的么"
    # 源消息被清理（发出 delete 语句）
    assert db.last_delete is not None


@pytest.mark.asyncio
async def test_archive_to_warm_no_compression_when_disabled():
    db = _FakeDB()
    svc = ConversationArchiveService(db)
    svc._get_config = AsyncMock(return_value=_config(compression_enabled=False))
    svc._get_agent_name = AsyncMock(return_value=None)

    await svc._archive_to_warm(
        user_id=1, thread_id="t2", agent_id="a2", messages=[{"role": "user", "content": "hi"}],
        date_range_start=datetime(2026, 1, 1), date_range_end=datetime(2026, 1, 2),
    )
    content = db.added[0].compressed_content
    assert isinstance(content, bytes)
    assert b"hi" in content  # 未压缩，明文包含在 JSONL 中


# ---------------- 恢复（温层） ----------------
@pytest.mark.asyncio
async def test_restore_warm_rehydrates_messages():
    db = _FakeDB()
    svc = ConversationArchiveService(db)
    svc._get_config = AsyncMock(return_value=_config())
    svc._get_agent_name = AsyncMock(return_value="AgentA")

    msgs = _messages()
    await svc._archive_to_warm(
        user_id=1, thread_id="t1", agent_id="a1", messages=msgs,
        date_range_start=datetime(2026, 1, 1), date_range_end=datetime(2026, 1, 2),
    )
    archive = db.added[0]

    # restore 的 select 返回该归档
    db2 = _FakeDB(results=[SimpleNamespace(scalar_one_or_none=lambda: archive)])
    # 复用已用过的 svc 交互 db 会串态，重建服务指向 db2
    svc2 = ConversationArchiveService(db2)
    ok = await svc2.restore_archive(archive.id)

    assert ok is True
    assert archive.is_restored is True
    # 写回了一条 AgentMemory，content 与归档消息一致
    memory = db2.added[0]
    assert memory.thread_id == "t1"
    assert memory.memory_type == "conversation"
    assert memory.content["messages"] == msgs
    assert db2.commits == 1


@pytest.mark.asyncio
async def test_restore_missing_archive_raises():
    db = _FakeDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])
    svc = ConversationArchiveService(db)
    with pytest.raises(ValueError):
        await svc.restore_archive("missing")
