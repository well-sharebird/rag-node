"""
Orchestration Graph - 基于 LangGraph 的多 Agent 编排

将 Orchestration Engine 从手动任务分配重构为 LangGraph 的 Send API + 条件边

支持模式:
1. SUPERVISOR - 主管动态分配 Worker
2. ROUND_ROBIN - 轮流处理
3. VOTING - 并行执行后投票
4. PIPELINE - 顺序流水线
5. PARALLEL - 并行执行
"""
import logging
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages
from typing import Annotated
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage

logger = logging.getLogger(__name__)


class OrchestrationState(TypedDict):
    """
    编排状态
    """
    task: str
    workers: List[str]
    results: Dict[str, Any]
    current_worker: Optional[str]
    final_output: Optional[str]
    messages: Annotated[List[BaseMessage], add_messages]


class OrchestrationGraphBuilder:
    """
    编排图构建器

    根据模式动态构建不同的图结构
    """

    def __init__(self, workers: List[Dict[str, Any]]):
        """
        Args:
            workers: Worker 配置列表
                [{"id": "worker1", "role": "researcher", "prompt": "..."}, ...]
        """
        self.workers = workers

    def build(self, mode: str) -> Any:
        """
        根据模式构建图

        Args:
            mode: 编排模式 (supervisor, round_robin, voting, pipeline, parallel)

        Returns:
            CompiledStateGraph: 编译后的图
        """
        if mode == "supervisor":
            return self._build_supervisor_graph()
        elif mode == "round_robin":
            return self._build_round_robin_graph()
        elif mode == "voting":
            return self._build_voting_graph()
        elif mode == "pipeline":
            return self._build_pipeline_graph()
        elif mode == "parallel":
            return self._build_parallel_graph()
        else:
            raise ValueError(f"Unknown orchestration mode: {mode}")

    def _build_supervisor_graph(self) -> Any:
        """
        Supervisor 模式图

        流程:
        1. Supervisor 分析任务，决定下一个 Worker
        2. 执行选中的 Worker
        3. 回到 Supervisor，继续决策
        4. 任务完成后结束
        """
        from langgraph.graph import StateGraph

        graph = StateGraph(OrchestrationState)

        # Supervisor 节点
        graph.add_node("supervisor", self._create_supervisor_node())

        # Worker 节点
        for worker in self.workers:
            graph.add_node(
                f"worker_{worker['id']}",
                self._create_worker_node(worker)
            )

        # Supervisor 动态路由到 Worker
        graph.add_conditional_edges(
            "supervisor",
            self._route_to_worker,
            {w["id"]: f"worker_{w['id']}" for w in self.workers} | {"FINISH": END}
        )

        # Worker 完成后回到 Supervisor
        for worker in self.workers:
            graph.add_edge(f"worker_{worker['id']}", "supervisor")

        graph.add_edge(START, "supervisor")

        return graph.compile()

    def _build_round_robin_graph(self) -> Any:
        """
        Round Robin 模式图

        流程:
        1. 按顺序执行 Worker 1 → Worker 2 → ... → Worker N
        2. 每个 Worker 的输出是下一个 Worker 的输入
        """
        from langgraph.graph import StateGraph

        graph = StateGraph(OrchestrationState)

        # 添加所有 Worker 节点
        prev_node = None
        for i, worker in enumerate(self.workers):
            node_name = f"worker_{worker['id']}"
            graph.add_node(node_name, self._create_worker_node(worker))

            if prev_node is None:
                graph.add_edge(START, node_name)
            else:
                graph.add_edge(prev_node, node_name)

            prev_node = node_name

        # 最后一个 Worker 完成后结束
        if prev_node:
            graph.add_edge(prev_node, END)

        return graph.compile()

    def _build_voting_graph(self) -> Any:
        """
        Voting 模式图

        流程:
        1. 并行执行所有 Worker
        2. 收集所有结果
        3. 投票选择最佳结果
        """
        from langgraph.graph import StateGraph

        graph = StateGraph(OrchestrationState)

        # 添加分发器节点
        graph.add_node("distribute", self._create_distribute_node())

        # 添加所有 Worker 节点
        for worker in self.workers:
            graph.add_node(
                f"worker_{worker['id']}",
                self._create_worker_node(worker)
            )

        # 添加投票节点
        graph.add_node("vote", self._create_vote_node())

        # 分发器并行执行所有 Worker
        graph.add_edge(START, "distribute")
        graph.add_conditional_edges(
            "distribute",
            lambda state: "parallel",
            {f"worker_{w['id']}": f"worker_{w['id']}" for w in self.workers}
        )

        # 所有 Worker 完成后到投票节点
        for worker in self.workers:
            graph.add_edge(f"worker_{worker['id']}", "vote")

        graph.add_edge("vote", END)

        return graph.compile()

    def _build_pipeline_graph(self) -> Any:
        """
        Pipeline 模式图

        类似 Round Robin，但每个阶段有明确的输入输出转换
        """
        # Pipeline 实现类似 Round Robin，这里简化处理
        return self._build_round_robin_graph()

    def _build_parallel_graph(self) -> Any:
        """
        Parallel 模式图

        类似 Voting，但不需要投票，直接汇总结果
        """
        from langgraph.graph import StateGraph

        graph = StateGraph(OrchestrationState)

        # 添加分发器节点
        graph.add_node("distribute", self._create_distribute_node())

        # 添加所有 Worker 节点
        for worker in self.workers:
            graph.add_node(
                f"worker_{worker['id']}",
                self._create_worker_node(worker)
            )

        # 添加汇总节点
        graph.add_node("aggregate", self._create_aggregate_node())

        # 分发器并行执行所有 Worker
        graph.add_edge(START, "distribute")
        graph.add_conditional_edges(
            "distribute",
            lambda state: "parallel",
            {f"worker_{w['id']}": f"worker_{w['id']}" for w in self.workers}
        )

        # 所有 Worker 完成后到汇总节点
        for worker in self.workers:
            graph.add_edge(f"worker_{worker['id']}", "aggregate")

        graph.add_edge("aggregate", END)

        return graph.compile()

    # ============================================================
    # 节点创建函数
    # ============================================================

    def _create_supervisor_node(self):
        """创建 Supervisor 节点"""
        async def supervisor_node(state: OrchestrationState) -> Dict[str, Any]:
            """
            Supervisor 节点 - 决定下一个 Worker

            实际实现需要调用 LLM 决定
            """
            task = state.get("task", "")
            results = state.get("results", {})

            # 简单实现：按顺序选择 Worker
            completed_workers = list(results.keys())
            remaining_workers = [w for w in self.workers if w["id"] not in completed_workers]

            if not remaining_workers:
                return {"current_worker": "FINISH"}

            next_worker = remaining_workers[0]
            return {"current_worker": next_worker["id"]}

        return supervisor_node

    def _create_worker_node(self, worker: Dict[str, Any]):
        """创建 Worker 节点"""
        async def worker_node(state: OrchestrationState) -> Dict[str, Any]:
            """
            Worker 节点 - 执行具体任务

            实际实现需要调用具体的 Agent 或工具
            """
            task = state.get("task", "")
            worker_id = worker["id"]
            worker_role = worker.get("role", "assistant")

            logger.info(f"Worker {worker_id} ({worker_role}) executing task: {task}")

            # 模拟执行结果
            result = f"Result from {worker_id}"

            return {
                "results": {worker_id: result},
                "current_worker": worker_id,
            }

        return worker_node

    def _create_distribute_node(self):
        """创建分发器节点"""
        async def distribute_node(state: OrchestrationState) -> Dict[str, Any]:
            """分发任务给所有 Worker"""
            return {"current_worker": "all"}

        return distribute_node

    def _create_vote_node(self):
        """创建投票节点"""
        async def vote_node(state: OrchestrationState) -> Dict[str, Any]:
            """投票选择最佳结果"""
            results = state.get("results", {})

            # 简单实现：选择第一个结果
            # 实际应该实现投票逻辑
            for worker_id, result in results.items():
                return {"final_output": f"Selected: {result}"}

            return {"final_output": "No results"}

        return vote_node

    def _create_aggregate_node(self):
        """创建汇总节点"""
        async def aggregate_node(state: OrchestrationState) -> Dict[str, Any]:
            """汇总所有 Worker 结果"""
            results = state.get("results", {})

            aggregated = "\n\n".join([
                f"[{wid}] {result}"
                for wid, result in results.items()
            ])

            return {"final_output": aggregated}

        return aggregate_node

    # ============================================================
    # 路由函数
    # ============================================================

    def _route_to_worker(self, state: OrchestrationState) -> str:
        """路由到 Worker"""
        current = state.get("current_worker")
        if current == "FINISH":
            return "FINISH"
        return current


# ============================================================
# 便捷函数
# ============================================================

def build_orchestration_graph(
    workers: List[Dict[str, Any]],
    mode: str,
) -> Any:
    """
    构建编排图

    Args:
        workers: Worker 配置列表
        mode: 编排模式

    Returns:
        CompiledStateGraph: 编译后的图
    """
    builder = OrchestrationGraphBuilder(workers)
    return builder.build(mode)
