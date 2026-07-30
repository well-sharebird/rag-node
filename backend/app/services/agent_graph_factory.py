"""
Agent Graph Factory - 特殊复杂工作流的 StateGraph 构建器

⚠️ 注意：根据 DeerFlow 设计原则，本文件仅用于特殊复杂工作流场景。
默认情况下，所有 Agent 都应该使用 agent_factory.py 中的 create_agent() 工厂函数。

使用场景：
- 需要自定义图结构（多节点、条件分支、循环等）
- 需要精确控制节点执行顺序
- 需要自定义状态转换逻辑

标准 Agent 创建请使用：agent_factory.AgentFactory.create_agent()
"""
import logging
from typing import Optional, Any, AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.schemas.chat import ModelConfig

logger = logging.getLogger("app.services.agent_graph_factory")


# ============================================================
# Agent State (仅用于复杂工作流)
# ============================================================

from typing import TypedDict, List, Dict, Any
from typing_extensions import NotRequired
from langchain_core.messages import BaseMessage


class WorkflowState(TypedDict, total=False):
    """
    复杂工作流的状态 schema

    ⚠️ 注意：标准 Agent 使用 agent_factory 中的 AgentState
    """
    messages: List[BaseMessage]
    context: Dict[str, Any]
    current_step: str
    metadata: Dict[str, Any]
    plan: NotRequired[List[str]]
    todo_list: NotRequired[List[Dict[str, Any]]]


# ============================================================
# StateGraph Builder (特殊场景使用)
# ============================================================

class StateGraphBuilder:
    """
    StateGraph 构建器 - 仅用于特殊复杂工作流

    ⚠️ 注意：99% 的场景应该使用 create_agent()，只有需要自定义图结构时才使用此类
    """

    def __init__(self, model_gateway: Any, skill_registry: Any, db: Any):
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.db = db

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
        # 创建模型
        llm = await self._create_llm(model_config)

        # 创建图
        graph = StateGraph(WorkflowState)

        # 添加节点
        for node_name, node_func in nodes.items():
            graph.add_node(node_name, node_func)

        # 添加边
        for from_node, to_node in edges:
            if from_node == "START":
                graph.add_edge(START, to_node)
            elif to_node == "END":
                graph.add_edge(from_node, END)
            else:
                graph.add_edge(from_node, to_node)

        # 编译
        compiled = graph.compile()

        logger.info("Built custom workflow: %s with %d nodes", name, len(nodes))
        return compiled

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
