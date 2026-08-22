"""
运行时模块（参考 DeerFlow 设计）

提供：
- 中间件系统（AgentMiddleware, MiddlewareChain）
- 运行时上下文（RuntimeContext）
- 运行时引擎（RuntimeEngine, make_agent）
- 状态定义（AgentState, OrchestratorState）
- 内置中间件（ThreadData, Sandbox, ToolErrorHandling, etc.）
"""

from .middleware import (
    AgentMiddleware,
    RuntimeContext,
    MiddlewareChain,
)

from .engine import (
    RuntimeEngine,
    make_agent,
)

from .graph import (
    build_agent_graph,
    create_think_node,
    create_act_node,
    create_observe_node,
    create_permission_check_node,
    extract_reasoning,
    extract_tool_calls,
)

from .state import (
    AgentState,
    OrchestratorState,
    ExecutionResult,
)

from .builtins import (
    # 基础层
    ThreadDataMiddleware,
    SandboxMiddleware,
    ToolErrorHandlingMiddleware,
    DanglingToolCallMiddleware,
    
    # 功能层
    TitleMiddleware,
    MemoryMiddleware,
    LoopDetectionMiddleware,
    ClarificationMiddleware,
    
    # Phase 5: Hooks 迁移
    SecurityMiddleware,
    SessionLogMiddleware,
    CheckpointMiddleware,
    
    # 工厂
    build_default_middlewares,
)

from .adapters import (
    HooksAdapterMiddleware,
)

__all__ = [
    # 核心类
    "AgentMiddleware",
    "RuntimeContext",
    "MiddlewareChain",
    "RuntimeEngine",
    "make_agent",
    
    # 状态
    "AgentState",
    "OrchestratorState",
    
    # 图构建
    "build_agent_graph",
    "create_think_node",
    "create_act_node",
    "create_observe_node",
    "create_permission_check_node",
    "extract_reasoning",
    "extract_tool_calls",
    
    # 基础层中间件
    "ThreadDataMiddleware",
    "SandboxMiddleware",
    "ToolErrorHandlingMiddleware",
    "DanglingToolCallMiddleware",
    
    # 功能层中间件
    "TitleMiddleware",
    "MemoryMiddleware",
    "LoopDetectionMiddleware",
    "ClarificationMiddleware",
    
    # Phase 5: Hooks 迁移
    "SecurityMiddleware",
    "SessionLogMiddleware",
    "CheckpointMiddleware",
    
    # 适配器
    "HooksAdapterMiddleware",
    
    # 工厂
    "build_default_middlewares",
]
