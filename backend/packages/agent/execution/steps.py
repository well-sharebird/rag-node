"""Step / Turn 执行模型（P0）。

参考 DeepSeek Harness：
- **step**：一次「模型请求 + 工具调用」的最小执行单元，可独立追踪、拦截、跳过。
- **turn**：由多个 step 组成的一次完整用户请求处理（等价于现在的一次 run_stream）。

KnowRAG 现状是「一次 Plan 执行到底」，所有子 Agent 一次性派发、执行、聚合。
本模型把执行过程拆成可编排的 step 序列，从而支持：
- 逐 step 动态决策（P0-3）
- 逐 step 钩子拦截（P1）
- 逐 step 事件溯源 / 断点恢复（P1）
- 执行中的 agent.send 追加指令（P0-2）
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    """Step 类型"""
    PLAN = "plan"                  # 主 Agent 出 Plan
    DIRECT = "direct"              # 直接回答
    DISPATCH = "dispatch"          # 派发子 Agent（可含多个子任务）
    AGGREGATE = "aggregate"        # 聚合子结果
    TOOL = "tool"                  # 工具调用
    SUB_AGENT = "sub_agent"        # 单个子 Agent
    MODEL = "model"                # 单次模型请求
    CUSTOM = "custom"              # 自定义 step


class StepStatus(str, Enum):
    """Step 状态"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TurnStatus(str, Enum):
    """Turn 状态"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Step:
    """单个执行步骤。"""
    step_id: str
    type: StepType
    name: str = ""
    status: StepStatus = StepStatus.PENDING
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: int = 0
    parent_id: Optional[str] = None
    # 追加指令（agent.send），执行中动态影响本 step
    injections: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @classmethod
    def new(cls, type: StepType, name: str = "", **kw) -> "Step":
        return cls(
            step_id=kw.pop("step_id", None) or f"{type.value}_{uuid.uuid4().hex[:8]}",
            type=type,
            name=name or type.value,
            **kw,
        )

    def start(self) -> None:
        self.status = StepStatus.RUNNING
        self.started_at = time.time()

    def complete(self, output: Optional[Dict[str, Any]] = None) -> None:
        self.status = StepStatus.DONE
        self.output = output
        self.finished_at = time.time()
        self.duration_ms = self._elapsed()

    def fail(self, error: str) -> None:
        self.status = StepStatus.FAILED
        self.error = error
        self.finished_at = time.time()
        self.duration_ms = self._elapsed()

    def skip(self, reason: str = "") -> None:
        self.status = StepStatus.SKIPPED
        self.error = reason or None
        self.finished_at = time.time()

    def cancel(self, reason: str = "") -> None:
        self.status = StepStatus.CANCELLED
        self.error = reason or None
        self.finished_at = time.time()

    def add_injection(self, content: str, by: str = "user") -> None:
        """执行中追加指令（agent.send）。"""
        self.injections.append({"content": content, "by": by, "at": time.time()})

    def _elapsed(self) -> int:
        if self.started_at is None:
            return 0
        end = self.finished_at or time.time()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "type": self.type.value,
            "name": self.name,
            "status": self.status.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "injections": self.injections,
        }


@dataclass
class Turn:
    """一次完整用户请求执行。"""
    turn_id: str
    query: str
    status: TurnStatus = TurnStatus.PENDING
    steps: List["Step"] = field(default_factory=list)
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    duration_ms: int = 0

    @classmethod
    def new(cls, query: str, **kw) -> "Turn":
        t = time.time()
        return cls(
            turn_id=kw.pop("turn_id", None) or f"turn_{int(t * 1000)}",
            query=query,
            **kw,
        )

    def add_step(self, step: Step) -> Step:
        self.steps.append(step)
        return step

    def start(self) -> None:
        self.status = TurnStatus.RUNNING

    def complete(self) -> None:
        self.status = TurnStatus.DONE
        self.finished_at = time.time()
        self._finalize()

    def fail(self) -> None:
        self.status = TurnStatus.FAILED
        self.finished_at = time.time()
        self._finalize()

    def cancel(self) -> None:
        self.status = TurnStatus.CANCELLED
        self.finished_at = time.time()
        self._finalize()

    def _finalize(self) -> None:
        if self.finished_at and self.created_at:
            self.duration_ms = int((self.finished_at - self.created_at) * 1000)

    def total_steps(self) -> int:
        return len(self.steps)

    def done_steps(self) -> int:
        return sum(1 for s in self.steps if s.status in (StepStatus.DONE, StepStatus.SKIPPED))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "query": self.query,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }


class ExecutionContext:
    """跨 step 传递的执行上下文，承载可动态调整的状态。

    替代 OrchestratorRuntime 中「传入 state 副作用 + 实例变量 _last_orchestrator_state」的
    反模式：执行期间的状态显式挂在此上下文，可按 step 演进，供钩子读取/改写。
    """
    def __init__(self, turn: Turn):
        self.turn = turn
        self.plan: Optional[Dict[str, Any]] = None        # 当前 plan（可被动态修改）
        self.user_id: Optional[int] = None
        self.session_id: Optional[str] = None
        self.agent_id: Optional[str] = None
        self.step_index: int = 0
        # 供钩子/事件溯源共享的 key-value
        self.vars: Dict[str, Any] = {}

    @property
    def current_step(self) -> Optional[Step]:
        if 0 <= self.step_index < len(self.turn.steps):
            return self.turn.steps[self.step_index]
        return None

    def register(self, step: Step) -> Step:
        self.turn.add_step(step)
        return step
