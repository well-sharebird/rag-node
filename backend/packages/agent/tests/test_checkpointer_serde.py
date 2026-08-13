"""
#4: DatabaseCheckpointSaver 序列化往返测试

之前 checkpointer 失效根因：put 存裸 Checkpoint（含 LangChain BaseMessage）进 JSONB，
get_tuple 读回即崩。修复后 put/_get 均经 _ser_bytes/_deser_bytes（JsonPlusSerializer+base64）。

本测试用 mock 同步 Session 验证：
    - _ser_bytes/_deser_bytes 单值往返（含 HumanMessage）
    - put → 存的是 base64 字符串（可 JSON 化），非裸对象
    - put 后 get_tuple 能读回与写入等值（含消息 channel）
    - put_writes 追加写序列化、list 反序列化
"""
import base64

import pytest
from langchain_core.messages import HumanMessage

# 先导入全部模型以满足 SQLAlchemy mapper 注册顺序（User→TokenUsage→AgentMemory ...）
import app.models  # noqa: F401

from packages.agent.services.agent_checkpoint_service import (
    DatabaseCheckpointSaver,
    _deser_bytes,
    _ser_bytes,
)


class _SyncDB:
    """最小同步 Session mock：先无记录（put 建新），后回放已存 AgentMemory。"""

    def __init__(self):
        self.memory = None
        self.commits = 0

    def execute(self, stmt):
        class _Result:
            def __init__(self, memory):
                self._memory = memory

            def scalar_one_or_none(self):
                return self._memory

            def scalar(self):
                return self._memory

            def scalars(self):
                class _Rows:
                    def __init__(self, mem):
                        self._mem = mem

                    def all(self):
                        return [self._mem] if self._mem else []
                return _Rows(self._memory)
        return _Result(self.memory)

    def add(self, obj):
        self.memory = obj

    def commit(self):
        self.commits += 1


def _sample_checkpoint():
    return {
        "v": 1,
        "ts": "2026-08-13T00:00:00Z",
        "channel_values": {"messages": [HumanMessage(content="你好世界")]},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }


def _sample_metadata():
    return {"source": "input", "step": 1, "writes": None, "score": None}


def _config(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def test_ser_deser_single_value_roundtrip():
    payload = _sample_checkpoint()
    s = _ser_bytes(payload)
    # 必须是 base64 可解码字符串（写入 JSONB 的前提），而非裸对象
    assert isinstance(s, str)
    base64.b64decode(s)
    out = _deser_bytes(s)
    assert out["channel_values"]["messages"][0].content == "你好世界"
    assert isinstance(out["channel_values"]["messages"][0], HumanMessage)


def test_put_roundtrip_get_tuple():
    db = _SyncDB()
    saver = DatabaseCheckpointSaver(db)
    cfg = _config("1:sub-a:default")

    saver.put(cfg, _sample_checkpoint(), _sample_metadata(), {})

    # 存进 DB 的是 base64 字符串（JsonPlusSerializer 输出经 b64），非裸 Checkpoint
    content = db.memory.content
    assert isinstance(content["checkpoint"], str)
    assert "channel_values" not in content["checkpoint"]

    # get_tuple 从同一 memory 读回，等值恢复
    tup = saver.get_tuple(cfg)
    assert tup is not None
    assert tup.checkpoint["channel_values"]["messages"][0].content == "你好世界"
    assert tup.metadata["step"] == 1


def test_put_writes_serializes_and_list_reads_back():
    db = _SyncDB()
    saver = DatabaseCheckpointSaver(db)
    cfg = _config("1:sub-a:default")

    saver.put(cfg, _sample_checkpoint(), _sample_metadata(), {})
    saver.put_writes(cfg, [("messages", HumanMessage(content="待写"))], task_id="t1")

    # pending_writes 存的是序列化字符串
    stored = db.memory.content["pending_writes"]
    assert stored and isinstance(stored[0], str)

    # list 反序列化回读
    tups = list(saver.list(cfg))
    assert len(tups) == 1
    writes = tups[0].pending_writes
    # pending_writes 是"写块"列表，每块是一组 (channel, value) 元组
    assert writes and writes[0][0][1].content == "待写"
