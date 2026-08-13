"""
Runtime 层 - 封装 LangGraph 执行能力

解决"怎么跑"的问题：
- 持久化执行 (CheckpointSaver)
- 流式支持 (astream/stream_mode)
- 人机协作中断 (interrupt/resume)
- 线程级持久化 (thread_id 隔离)
- 状态快照 (get_state/patch_state)
"""
from packages.agent.runtime.config import RuntimeConfig, HarnessConfig
from packages.agent.runtime.state import ExecutionResult, HarnessState, TAOState

__all__ = [
    "RuntimeConfig",
    "HarnessConfig",
    "ExecutionResult",
    "HarnessState",
    "TAOState",
]
