"""Runtime Engine - LangGraph 层（状态 + TAO 图构建 + 检查点）

三层铁律下本包只承载 LangGraph 运行时编排组件（State/节点/图构建/Checkpoint），
治理归 `core.harness`，能力归 LangChain。
- 状态：`state.py`（HarnessState/TAOState/ExecutionResult/reducers）
- 图：`tao_graph.py`（TAO 循环图）
- 检查点：`checkpointer.py`（LangGraph 异步检查点持久化适配）

遗留：`parser.py` 为待清理模块，无外部引用。
"""
from packages.agent.runtime_engine.state import (
    ExecutionResult,
    HarnessState,
    TAOState,
    append_lists,
    append_string,
    extract_tasks,
    update_todos_from_message,
)
from packages.agent.runtime_engine.tao_graph import (
    build_tao_graph,
    create_act_node,
    create_observe_node,
    create_permission_check_node,
    create_should_act_router,
    create_tao_agent,
    create_think_node,
)

__all__ = [
    # state
    "TAOState",
    "HarnessState",
    "ExecutionResult",
    "append_lists",
    "append_string",
    "extract_tasks",
    "update_todos_from_message",
    # graph
    "build_tao_graph",
    "create_think_node",
    "create_act_node",
    "create_permission_check_node",
    "create_observe_node",
    "create_should_act_router",
    "create_tao_agent",
]
