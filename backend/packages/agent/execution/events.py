"""Turn/Step 结构化事件流（P0）。

参考 DeepSeek Harness Turn Flow：
    turn/start → claim input → pre-step hook → step/start → agent/request
    → llm/stream → tool calls → step/end → post-step hook → 判断是否继续 → turn/end

在现有 run_stream 的扁平事件（orchestrator_plan / sub_agent / token / tool_event）之上，
补充结构化 step 生命周期事件，供前端追迹、钩子拦截、事件溯源。
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Optional, Union


class ExecutionEventType(str, Enum):
    """结构化执行事件类型。"""
    TURN_START = "turn/start"
    TURN_END = "turn/end"
    STEP_START = "step/start"
    STEP_END = "step/end"
    PLAN_CREATED = "plan/created"
    PLAN_UPDATED = "plan/updated"
    AGENT_REQUEST = "agent/request"        # agent send / inject
    LLM_STREAM = "llm/stream"              # 模型逐 token
    TOOL_START = "tool/start"
    TOOL_END = "tool/end"
    SUB_AGENT_START = "sub_agent/start"
    SUB_AGENT_END = "sub_agent/end"
    CHECKPOINT = "checkpoint"


class ExecutionEvent:
    """一个结构化执行事件。"""
    __slots__ = ("type", "turn_id", "step_id", "data", "ts")

    def __init__(self, type: Union[ExecutionEventType, str], turn_id: Optional[str] = None,
                 step_id: Optional[str] = None, data: Optional[Dict[str, Any]] = None):
        import time
        self.type = type.value if isinstance(type, ExecutionEventType) else type
        self.turn_id = turn_id
        self.step_id = step_id
        self.data = data or {}
        self.ts = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "turn_id": self.turn_id,
            "step_id": self.step_id,
            "data": self.data,
            "ts": self.ts,
        }


class ExecutionEventStream:
    """结构化事件流：后台任务产事件，消费者 drain。

    与 run_stream 现有 asyncio.Queue sink 同构，但统一承载 ExecutionEvent（而非原生 dict）。
    兼容：内部保留 sink dict 事件，供现有 /execute/stream 直接消费。
    """
    def __init__(self):
        self._queue: "asyncio.Queue[ExecutionEvent]" = asyncio.Queue()

    def publish(self, type: Union[ExecutionEventType, str], turn_id=None, step_id=None, data=None) -> None:
        ev = ExecutionEvent(type, turn_id=turn_id, step_id=step_id, data=data)
        self._queue.put_nowait(ev)

    async def get(self) -> ExecutionEvent:
        return await self._queue.get()

    def try_get(self) -> Optional[ExecutionEvent]:
        if self._queue.empty():
            return None
        return self._queue.get_nowait()

    def empty(self) -> bool:
        return self._queue.empty()

    async def __aiter__(self) -> AsyncGenerator[ExecutionEvent, None]:
        while True:
            yield await self._queue.get()
