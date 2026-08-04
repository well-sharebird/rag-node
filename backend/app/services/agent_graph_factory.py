"""
Agent Graph Factory - 特殊复杂工作流的 StateGraph 构建器

⚠️ 注意：根据 DeerFlow 设计原则，本文件仅用于特殊复杂工作流场景。
默认情况下，所有 Agent 都应该使用 agent_factory.py 中的 create_agent() 工厂函数。

使用场景：
- 需要自定义图结构（多节点、条件分支、循环等）
- 需要精确控制节点执行顺序
- 需要自定义状态转换逻辑
- 需要并行执行、子图嵌套

标准 Agent 创建请使用：agent_factory.AgentFactory.create_agent()

增强功能 (Phase 4):
- 并行节点执行
- 条件分支（基于 LLM 决策）
- 循环和重试
- 子图嵌套
- 运行时配置覆盖
"""
import logging
from typing import Optional, Any, AsyncGenerator, Callable, Union, Literal
from contextlib import asynccontextmanager
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.schemas.chat import ModelConfig

logger = logging.getLogger("app.services.agent_graph_factory")


# ============================================================
# Agent State (仅用于复杂工作流)
# ============================================================

from typing import TypedDict, List, Dict, Any, Annotated
from typing_extensions import NotRequired
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class WorkflowState(TypedDict, total=False):
    """
    复杂工作流的状态 schema

    ⚠️ 注意：标准 Agent 使用 agent_factory 中的 AgentState

    字段说明：
    - messages: 消息历史（自动合并）
    - context: 上下文数据（自定义字典）
    - current_step: 当前执行步骤
    - metadata: 元数据（用户 ID、Agent ID 等）
    - plan: 执行计划列表
    - todo_list: 待办事项列表
    - parallel_results: 并行执行结果
    - loop_count: 循环计数
    - error_history: 错误历史
    """
    # 核心字段
    messages: Annotated[List[BaseMessage], add_messages]
    context: Annotated[Dict[str, Any], lambda a, b: {**a, **b}]
    current_step: str
    metadata: Dict[str, Any]

    # 扩展字段（使用 Annotated 支持并发更新）
    plan: NotRequired[List[str]]
    todo_list: NotRequired[List[Dict[str, Any]]]
    parallel_results: NotRequired[Dict[str, Any]]
    loop_count: NotRequired[int]
    error_history: NotRequired[List[Dict[str, Any]]]
    current_step: NotRequired[str]


# ============================================================
# StateGraph Builder (特殊场景使用)
# ============================================================

class StateGraphBuilder:
    """
    StateGraph 构建器 - 仅用于特殊复杂工作流

    ⚠️ 注意：99% 的场景应该使用 create_agent()，只有需要自定义图结构时才使用此类

    增强功能 (Phase 4):
    - 并行节点执行
    - 条件分支（基于 LLM 决策）
    - 循环和重试
    - 子图嵌套
    - 运行时配置覆盖
    """

    def __init__(self, model_gateway: Any, skill_registry: Any, db: Any):
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.db = db
        self._subgraph_cache: dict[str, CompiledStateGraph] = {}

    # ============================================================
    # 核心构建方法
    # ============================================================

    async def build_custom_workflow(
        self,
        name: str,
        nodes: dict[str, Any],
        edges: list[tuple[str, str]],
        model_config: ModelConfig,
        system_prompt: str,
    ) -> CompiledStateGraph:
        """
        构建自定义工作流

        Args:
            name: 工作流名称
            nodes: 节点字典 {node_name: node_function}
            edges: 边列表 [(from_node, to_node), ...]
            model_config: 模型配置
            system_prompt: 系统提示词

        Returns:
            CompiledStateGraph
        """
        llm = await self._create_llm(model_config)
        graph = StateGraph(WorkflowState)

        for node_name, node_func in nodes.items():
            graph.add_node(node_name, node_func)

        for from_node, to_node in edges:
            if from_node == "START":
                graph.add_edge(START, to_node)
            elif to_node == "END":
                graph.add_edge(from_node, END)
            else:
                graph.add_edge(from_node, to_node)

        # 确保有入口点
        has_entrypoint = any(from_node == "START" for from_node, _ in edges)
        if not has_entrypoint and nodes:
            # 自动添加从 START 到第一个节点的边
            first_node = list(nodes.keys())[0]
            graph.add_edge(START, first_node)

        compiled = graph.compile()
        logger.info("Built custom workflow: %s with %d nodes", name, len(nodes))
        return compiled

    # ============================================================
    # 并行执行
    # ============================================================

    async def build_parallel_workflow(
        self,
        name: str,
        parallel_nodes: dict[str, Callable],
        aggregator: Callable,
        model_config: ModelConfig,
        system_prompt: str,
    ) -> CompiledStateGraph:
        """
        构建并行执行工作流

        Args:
            name: 工作流名称
            parallel_nodes: 并行节点字典 {node_name: node_function}
            aggregator: 聚合函数，用于合并并行结果
            model_config: 模型配置
            system_prompt: 系统提示词

        Returns:
            CompiledStateGraph

        示例：
            # 三个专家并行回答，然后聚合
            parallel_nodes = {
                "expert_a": create_expert_node("领域 A"),
                "expert_b": create_expert_node("领域 B"),
                "expert_c": create_expert_node("领域 C"),
            }
            aggregator = aggregate_parallel_results
        """
        llm = await self._create_llm(model_config)

        graph = StateGraph(WorkflowState)

        # 添加起始节点（分发任务）
        async def dispatcher(state: WorkflowState):
            """分发任务到并行节点"""
            return {"context": {"parallel_start": True}}

        graph.add_node("dispatcher", dispatcher)

        # 添加并行节点
        for node_name, node_func in parallel_nodes.items():
            graph.add_node(node_name, node_func)
            graph.add_edge("dispatcher", node_name)

        # 添加聚合节点
        graph.add_node("aggregator", aggregator)

        # 所有并行节点完成后执行聚合
        for node_name in parallel_nodes.keys():
            graph.add_edge(node_name, "aggregator")

        graph.add_edge(START, "dispatcher")
        graph.add_edge("aggregator", END)

        compiled = graph.compile()
        logger.info("Built parallel workflow: %s with %d parallel nodes", name, len(parallel_nodes))
        return compiled

    # ============================================================
    # 条件分支
    # ============================================================

    async def build_conditional_workflow(
        self,
        name: str,
        branches: dict[str, dict[str, Any]],
        condition_func: Callable,
        model_config: ModelConfig,
        system_prompt: str,
    ) -> CompiledStateGraph:
        """
        构建条件分支工作流

        Args:
            name: 工作流名称
            branches: 分支字典 {branch_name: {nodes: ..., edges: ...}}
            condition_func: 条件判断函数，返回分支名称
            model_config: 模型配置
            system_prompt: 系统提示词

        Returns:
            CompiledStateGraph

        示例：
            # 根据问题类型选择不同分支
            branches = {
                "code_review": {...},
                "doc_write": {...},
                "research": {...},
            }
        """
        llm = await self._create_llm(model_config)

        graph = StateGraph(WorkflowState)

        # 添加条件判断节点
        async def conditional_router(state: WorkflowState):
            """根据条件选择分支"""
            result = condition_func(state)
            branch_name = result.get("branch", "default")
            return {"current_step": f"routing_to_{branch_name}"}

        graph.add_node("router", conditional_router)

        # 添加所有分支的节点
        all_nodes = set()
        for branch_name, branch_config in branches.items():
            for node_name, node_func in branch_config.get("nodes", {}).items():
                full_name = f"{branch_name}_{node_name}"
                graph.add_node(full_name, node_func)
                all_nodes.add((branch_name, full_name))

        # 从 router 到各分支的起始节点
        for branch_name, branch_config in branches.items():
            start_nodes = branch_config.get("start_nodes", [])
            for start_node in start_nodes:
                full_name = f"{branch_name}_{start_node}"
                graph.add_edge("router", full_name)

        # 添加分支内部边
        for branch_name, branch_config in branches.items():
            for from_node, to_node in branch_config.get("edges", []):
                full_from = f"{branch_name}_{from_node}"
                full_to = f"{branch_name}_{to_node}"
                graph.add_edge(full_from, full_to)

        # 所有分支汇聚到 END
        end_nodes = set()
        for branch_name, branch_config in branches.items():
            for end_node in branch_config.get("end_nodes", []):
                end_nodes.add(f"{branch_name}_{end_node}")

        for end_node in end_nodes:
            graph.add_edge(end_node, END)

        graph.add_edge(START, "router")

        compiled = graph.compile()
        logger.info("Built conditional workflow: %s with %d branches", name, len(branches))
        return compiled

    # ============================================================
    # 循环和重试
    # ============================================================

    async def build_loop_workflow(
        self,
        name: str,
        loop_body: Callable,
        condition_func: Callable,
        max_iterations: int = 5,
        model_config: Optional[ModelConfig] = None,
    ) -> CompiledStateGraph:
        """
        构建循环工作流

        Args:
            name: 工作流名称
            loop_body: 循环体函数
            condition_func: 继续条件函数，返回 True 则继续循环
            max_iterations: 最大迭代次数
            model_config: 模型配置（可选）

        Returns:
            CompiledStateGraph

        示例：
            # 代码生成 - 审查 - 修改循环
            loop_body = generate_and_review_code
            condition_func = lambda state: not code_is_acceptable(state)
        """
        graph = StateGraph(WorkflowState)

        # 初始化循环计数
        async def init_loop(state: WorkflowState):
            return {"loop_count": 0, "context": {"max_iterations": max_iterations}}

        graph.add_node("init", init_loop)

        # 循环体节点
        graph.add_node("loop_body", loop_body)

        # 条件检查节点
        async def check_condition(state: WorkflowState):
            loop_count = state.get("loop_count", 0)
            should_continue = condition_func(state)

            if should_continue and loop_count < max_iterations:
                return {"loop_count": loop_count + 1, "current_step": "continue_loop"}
            else:
                return {"current_step": "exit_loop"}

        graph.add_node("check_condition", check_condition)

        # 循环出口（最终响应）
        async def finalize(state: WorkflowState):
            return {"current_step": "completed"}

        graph.add_node("finalize", finalize)

        # 连接边
        graph.add_edge(START, "init")
        graph.add_edge("init", "loop_body")
        graph.add_edge("loop_body", "check_condition")

        # 条件边
        graph.add_conditional_edges(
            "check_condition",
            lambda s: "loop_body" if s.get("loop_count", 0) < max_iterations and s.get("context", {}).get("should_continue", False) else "finalize",
            {
                "loop_body": "loop_body",
                "finalize": "finalize",
            }
        )

        graph.add_edge("finalize", END)

        compiled = graph.compile()
        logger.info("Built loop workflow: %s (max_iterations=%d)", name, max_iterations)
        return compiled

    # ============================================================
    # 子图嵌套
    # ============================================================

    def register_subgraph(self, name: str, subgraph: CompiledStateGraph):
        """
        注册子图供复用

        Args:
            name: 子图名称
            subgraph: 已编译的子图
        """
        self._subgraph_cache[name] = subgraph
        logger.info("Registered subgraph: %s", name)

    async def build_nested_workflow(
        self,
        name: str,
        subgraphs: dict[str, str],  # {node_name: subgraph_name}
        entry_points: dict[str, str],  # {subgraph_name: entry_node}
        model_config: Optional[ModelConfig] = None,
    ) -> CompiledStateGraph:
        """
        构建嵌套子图工作流

        Args:
            name: 工作流名称
            subgraphs: 子图节点映射 {node_name: subgraph_name}
            entry_points: 各子图的入口节点
            model_config: 模型配置

        Returns:
            CompiledStateGraph
        """
        graph = StateGraph(WorkflowState)

        # 添加子图节点
        for node_name, subgraph_name in subgraphs.items():
            if subgraph_name in self._subgraph_cache:
                subgraph = self._subgraph_cache[subgraph_name]
                graph.add_node(node_name, subgraph)
            else:
                logger.warning("Subgraph not found: %s", subgraph_name)

        # 连接子图
        subgraph_list = list(subgraphs.keys())
        for i, node_name in enumerate(subgraph_list):
            if i == 0:
                graph.add_edge(START, node_name)
            else:
                prev_node = subgraph_list[i - 1]
                graph.add_edge(prev_node, node_name)

            # 最后一个子图连接到 END
            if i == len(subgraph_list) - 1:
                graph.add_edge(node_name, END)

        compiled = graph.compile()
        logger.info("Built nested workflow: %s with %d subgraphs", name, len(subgraphs))
        return compiled

    # ============================================================
    # 工具方法
    # ============================================================

    async def _create_llm(self, model_config: ModelConfig) -> Any:
        from app.services.agent_runtime_service import create_langchain_llm
        return await create_langchain_llm(model_config, self.db)


# ============================================================
# 简化的工厂函数 (保留向后兼容)
# ============================================================

@asynccontextmanager
async def create_simple_graph(
    llm: Any,
    system_prompt: str,
    tools: list = None,
) -> AsyncGenerator[CompiledStateGraph, None]:
    """
    创建简单的单节点图

    ⚠️ 注意：标准场景请使用 create_agent()，此函数仅用于需要显式图控制的场景
    """
    tools = tools or []
    if tools:
        llm = llm.bind_tools(tools)

    def agent_node(state: WorkflowState):
        messages = state.get("messages", [])
        if messages and not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        elif not messages:
            messages = [SystemMessage(content=system_prompt)]

        response = llm.invoke(messages)
        return {"messages": messages + [response]}

    graph = StateGraph(WorkflowState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)

    yield graph.compile()


# ============================================================
# 预定义节点函数
# ============================================================

def create_llm_node(
    llm: Any,
    system_prompt: str,
    node_name: str = "agent",
) -> Callable:
    """
    创建 LLM 节点

    Args:
        llm: LangChain LLM 实例
        system_prompt: 系统提示词
        node_name: 节点名称

    Returns:
        节点函数
    """
    async def llm_node(state: WorkflowState) -> WorkflowState:
        messages = state.get("messages", [])

        if messages and not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        elif not messages:
            messages = [SystemMessage(content=system_prompt)]

        response = await llm.ainvoke(messages)
        return {"messages": messages + [response], "current_step": node_name}

    return llm_node


def create_tool_node(
    tool_func: Callable,
    node_name: str = "tool",
) -> Callable:
    """
    创建工具节点

    Args:
        tool_func: 工具函数
        node_name: 节点名称

    Returns:
        节点函数
    """
    async def tool_node(state: WorkflowState) -> WorkflowState:
        messages = state.get("messages", [])
        context = state.get("context", {})

        try:
            result = await tool_func(messages, context)
            return {
                "messages": messages + [AIMessage(content=str(result))],
                "current_step": node_name,
            }
        except Exception as e:
            return {
                "messages": messages + [AIMessage(content=f"Error: {str(e)}")],
                "current_step": node_name,
                "error_history": state.get("error_history", []) + [{"node": node_name, "error": str(e)}],
            }

    return tool_node


def create_router_node(
    route_func: Callable,
    routes: dict[str, str],
) -> Callable:
    """
    创建路由节点

    Args:
        route_func: 路由判断函数，返回路由键
        routes: 路由映射 {route_key: next_node_name}

    Returns:
        节点函数
    """
    async def router_node(state: WorkflowState) -> WorkflowState:
        route_key = await route_func(state)
        next_node = routes.get(route_key, "default")
        return {"current_step": f"routing_to_{next_node}"}

    return router_node


# ============================================================
# 简化的工厂函数 (保留向后兼容)
# ============================================================

@asynccontextmanager
async def create_simple_graph(
    llm: Any,
    system_prompt: str,
    tools: list = None,
) -> AsyncGenerator[CompiledStateGraph, None]:
    """
    创建简单的单节点图

    ⚠️ 注意：标准场景请使用 create_agent()，此函数仅用于需要显式图控制的场景
    """
    tools = tools or []
    if tools:
        llm = llm.bind_tools(tools)

    def agent_node(state: WorkflowState):
        messages = state.get("messages", [])
        from langchain_core.messages import SystemMessage

        if messages and not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        elif not messages:
            messages = [SystemMessage(content=system_prompt)]

        response = llm.invoke(messages)
        return {"messages": messages + [response]}

    graph = StateGraph(WorkflowState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)

    yield graph.compile()
