"""
Runtime Engine - Agent 运行时执行引擎

注意：此模块保留用于向后兼容，但大部分组件已重构。

迁移指南:
    # 旧方式 (已弃用)
    from packages.agent.runtime_engine import OrchestrationEngine, MemoryEngine, ActionEngine

    # 新方式 (推荐)
    from packages.agent.orchestrator.graph import OrchestratorRuntime
    from packages.agent.runtime_engine.tao_graph import build_tao_graph
    # 注：多 Agent 采用主从编排（主 Agent + 子 Agent 子图），orchestration_graph 已移除；
    #     运行时统一为 OrchestratorRuntime（含通用执行/超时/重试/时间旅行能力）
    from packages.agent.runtime_engine.permission import PermissionEngine

详见：REFACTOR_PLAN.md
"""
import warnings

# 发出弃用警告
warnings.warn(
    "The runtime_engine modules are deprecated. "
    "Please use the new three-layer architecture: runtime, harness, and langgraph components. "
    "See REFACTOR_PLAN.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

# 保留的组件 (未删除)
from packages.agent.runtime_engine.permission import PermissionEngine
from packages.agent.runtime_engine.parser import OutputParser
from packages.agent.runtime_engine.token_budget import TokenBudgetManager, TokenBudgetConfig

# 兼容旧导入 - 使用占位符
class _DeprecatedEngine:
    """占位符类 - 用于已删除的引擎"""
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "This engine has been removed. "
            "Please use the unified runtime: OrchestratorRuntime "
            "for orchestration/execution, built on the TAO Graph."
        )

OrchestrationEngine = _DeprecatedEngine
MemoryEngine = _DeprecatedEngine
ActionEngine = _DeprecatedEngine
GovernanceEngine = _DeprecatedEngine
AgentLoopEngine = _DeprecatedEngine

# 兼容旧状态枚举
class LoopState:
    """循环状态 - 已弃用"""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class LoopContext:
    """循环上下文 - 已弃用"""
    pass

__all__ = [
    "PermissionEngine",
    "OutputParser",
    "TokenBudgetManager",
    "TokenBudgetConfig",
    "LoopState",
    "LoopContext",
]
