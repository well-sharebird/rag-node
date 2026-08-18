"""执行框架：Step 驱动的事件溯源执行模型（参考 DeepSeek Harness）。

将 KnowRAG 从「一次 Plan 执行到底」升级为「Step 驱动、事件溯源、可插拔钩子」：

- steps    : Step / Turn 执行模型（P0）
- events   : Turn/Step 结构化事件流（P0）
- hooks    : Pre/Post-Step 钩子与 waterfall 拦截器（P1）
- sourcing : 会话事件日志 / 事件溯源状态 / 检查点（P1）
- lifecycle: Agent 状态机 / fork / 并发（P2）
"""
from packages.agent.execution.steps import (
    Step,
    StepType,
    StepStatus,
    Turn,
    TurnStatus,
    ExecutionContext,
)
from packages.agent.execution.events import (
    ExecutionEventType,
    ExecutionEvent,
    ExecutionEventStream,
)

__all__ = [
    "Step",
    "StepType",
    "StepStatus",
    "Turn",
    "TurnStatus",
    "ExecutionContext",
    "ExecutionEventType",
    "ExecutionEvent",
    "ExecutionEventStream",
]
