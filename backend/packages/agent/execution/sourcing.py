"""事件溯源 / 会话日志 / 检查点（P1）。

参考 DeepSeek Harness：
- **SessionLog**：追加式事件日志（事件是唯一真相来源）。消息历史可从日志推导
  （derive_messages），无需独立 CRUD 历史存储。
- **EventSourcedState**：状态是事件的投影，可从日志重放重建。
- **ExecutionCheckpoint**：每 step 保存检查点，崩溃后可恢复继续执行。
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 持久化后端抽象：session 内默认内存实现；生产可替换为 DB/Redis。
PersistBackend = Callable[[str, Dict[str, Any]], Awaitable[None]]   # save(key, value)
LoadBackend = Callable[[str], Awaitable[Optional[Dict[str, Any]]]]  # load(key)


class MemoryStore:
    """内存持久化后端（测试/默认）。"""
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}

    async def save(self, key: str, value: Dict[str, Any]) -> None:
        self._data[key] = dict(value)

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        return self._data.get(key)

    async def append(self, key: str, value: Dict[str, Any]) -> None:
        lst = self._data.setdefault(key, [])
        lst = list(lst) + [value]
        self._data[key] = lst


class SessionLog:
    """会话事件日志（Event Sourcing 追加式日志）。"""
    def __init__(self, store: Optional[MemoryStore] = None):
        self._store = store or MemoryStore()

    async def append(self, session_id: str, event_type: str, payload: Dict[str, Any],
                     turn: int, step: Optional[int] = None) -> None:
        record = {
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
            "turn": turn,
            "step": step,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        await self._store.append(f"session_log:{session_id}", record)

    async def events(self, session_id: str) -> List[Dict[str, Any]]:
        return self._store._data.get(f"session_log:{session_id}", [])

    async def derive_messages(self, session_id: str) -> List[Dict[str, str]]:
        """从日志推导模型消息历史（替代独立历史存储）。"""
        messages: List[Dict[str, str]] = []
        for e in await self.events(session_id):
            et, p = e["event_type"], e["payload"]
            if et == "user/message":
                messages.append({"role": "user", "content": p.get("content", "")})
            elif et == "assistant/message":
                content = p.get("content", "") or ""
                reasoning = p.get("reasoning") or ""
                if reasoning:
                    content = f"[reasoning] {reasoning}\n" + content
                messages.append({"role": "assistant", "content": content})
            elif et == "tool/result":
                messages.append({"role": "tool", "content": p.get("content", "")[:2000]})
        return messages


class EventSourcedState:
    """事件溯源状态：状态是事件的投影。"""
    def __init__(self, log: SessionLog):
        self._log = log

    def apply_to_state(self, state: Dict[str, Any], event_type: str, payload: Dict[str, Any]) -> None:
        """把事件投影到内存状态。"""
        if event_type == "plan/created":
            state["plan"] = payload.get("plan") or payload
        elif event_type == "sub_agent/done":
            state.setdefault("sub_agent_results", []).append(payload)
        elif event_type == "token/accum":
            state["final_answer"] = (state.get("final_answer") or "") + (payload.get("content") or "")

    async def replay(self, session_id: str) -> Dict[str, Any]:
        """重放日志重建状态。"""
        state: Dict[str, Any] = {}
        for e in await self._log.events(session_id):
            self.apply_to_state(state, e["event_type"], e["payload"])
        return state


class ExecutionCheckpoint:
    """执行检查点：每 step 保存，崩溃后恢复。"""
    def __init__(self, store: Optional[MemoryStore] = None):
        self._store = store or MemoryStore()

    async def save(self, session_id: str, turn_id: str, step: Dict[str, Any],
                   state_snapshot: Dict[str, Any]) -> None:
        await self._store.save(f"checkpoint:{session_id}:{turn_id}", {
            "step": step,
            "state": state_snapshot,
            "saved_at": datetime.datetime.utcnow().isoformat(),
        })

    async def restore(self, session_id: str, turn_id: str) -> Optional[Dict[str, Any]]:
        return await self._store.load(f"checkpoint:{session_id}:{turn_id}")

    async def clear(self, session_id: str, turn_id: str) -> None:
        self._store._data.pop(f"checkpoint:{session_id}:{turn_id}", None)
