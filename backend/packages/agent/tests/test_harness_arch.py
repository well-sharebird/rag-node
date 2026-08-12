"""
Harness 架构测试

验证新的三层架构是否正常工作
"""
import pytest
import asyncio
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


# ============================================================
# Test 1: Runtime 层测试
# ============================================================

class TestRuntime:
    """Runtime 层测试"""

    def test_runtime_config_creation(self):
        """测试 RuntimeConfig 创建"""
        from packages.agent.runtime import RuntimeConfig

        config = RuntimeConfig(
            stream=True,
            timeout_seconds=300,
            token_budget=4096,
        )

        assert config.stream is True
        assert config.timeout_seconds == 300
        assert config.token_budget == 4096
        print("✅ RuntimeConfig creation test passed")

    def test_agent_runtime_creation(self):
        """测试 AgentRuntime 创建"""
        from packages.agent.runtime import AgentRuntime, RuntimeConfig

        runtime = AgentRuntime(config=RuntimeConfig())

        assert runtime.config.timeout_seconds == 300
        assert runtime.config.token_budget == 4096
        print("✅ AgentRuntime creation test passed")

    @pytest.mark.asyncio
    async def test_simple_graph_execution(self):
        """测试简单图执行"""
        from packages.agent.runtime import AgentRuntime, RuntimeConfig, ExecutionResult

        # 定义状态
        class SimpleState(TypedDict):
            messages: Annotated[List[str], add_messages]

        # 构建简单图
        def agent_node(state: SimpleState):
            return {"messages": [f"Response to: {state['messages'][-1]}"]}

        graph = StateGraph(SimpleState)
        graph.add_node("agent", agent_node)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)
        compiled = graph.compile()

        # 执行
        runtime = AgentRuntime(config=RuntimeConfig())
        result = await runtime.execute(
            graph=compiled,
            state={"messages": ["Hello"]},
            thread_id="test_1",
        )

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        print("✅ Simple graph execution test passed")


# ============================================================
# Test 2: TAO Graph 测试
# ============================================================

class TestTAOGraph:
    """TAO Graph 测试"""

    def test_tao_state_definition(self):
        """测试 TAOState 定义"""
        from packages.agent.runtime_engine.tao_graph import TAOState

        # 验证类型定义
        state: TAOState = {
            "messages": [],
            "reasoning": "",
            "tool_calls": [],
            "iteration": 0,
            "termination_reason": None,
        }
        assert state["iteration"] == 0
        print("✅ TAOState definition test passed")

    def test_should_act_router(self):
        """测试路由函数"""
        from packages.agent.runtime_engine.tao_graph import create_should_act_router

        router = create_should_act_router(max_iterations=10)

        # 测试无工具调用
        state_end = {
            "messages": [],
            "reasoning": "",
            "tool_calls": [],
            "iteration": 1,
            "termination_reason": None,
        }
        assert router(state_end) == "end"

        # 测试有工具调用
        state_act = {
            "messages": [],
            "reasoning": "",
            "tool_calls": [{"name": "search"}],
            "iteration": 1,
            "termination_reason": None,
        }
        assert router(state_act) == "act"

        # 测试最大迭代
        state_max = {
            "messages": [],
            "reasoning": "",
            "tool_calls": [{"name": "search"}],
            "iteration": 10,
            "termination_reason": None,
        }
        assert router(state_max) == "end"

        print("✅ should_act router test passed")


# ============================================================
# Test 3: Orchestration Graph 测试
# ============================================================
# 注：多 Agent 改用主从编排（主 Agent + 子 Agent 子图），
#     旧的 orchestration_graph（supervisor/round_robin/voting 死壳）已移除。

# ============================================================
# Test 4: Governance Callback 测试
# ============================================================

class TestGovernance:
    """Governance 测试"""

    def test_governance_engine_creation(self):
        """测试 GovernanceEngine 创建"""
        from packages.agent.runtime_engine.governance_callback import GovernanceEngine

        engine = GovernanceEngine()
        assert engine._active_traces == {}
        print("✅ GovernanceEngine creation test passed")

    def test_trace_lifecycle(self):
        """测试追踪生命周期"""
        from packages.agent.runtime_engine.governance_callback import (
            GovernanceEngine, ExecutionStep,
        )

        engine = GovernanceEngine()

        # 开始追踪
        trace_id = "test_trace_001"
        engine._active_traces[trace_id] = []

        # 添加步骤
        step = ExecutionStep(
            step_id="step_1",
            action="llm_call",
            timestamp="2024-01-01T00:00:00Z",
            duration_ms=100,
            metadata={"tokens": 100},
        )
        asyncio.run(engine.add_step(trace_id, step))

        assert len(engine._active_traces[trace_id]) == 1
        print("✅ Trace lifecycle test passed")

    def test_callback_handler_creation(self):
        """测试 Callback Handler 创建"""
        from packages.agent.runtime_engine.governance_callback import (
            GovernanceEngine, GovernanceCallbackHandler,
        )

        engine = GovernanceEngine()
        handler = GovernanceCallbackHandler(trace_id="test_001", engine=engine)

        assert handler.trace_id == "test_001"
        assert handler.engine == engine
        print("✅ CallbackHandler creation test passed")


# ============================================================
# Test 5: Harness 层测试
# ============================================================

class TestHarness:
    """Harness 层测试"""

    def test_harness_config_creation(self):
        """测试 HarnessConfig 创建"""
        from packages.agent.harness.config import HarnessConfig, CollaborationMode

        config = HarnessConfig(
            enable_planning_tools=True,
            collaboration_modes=[CollaborationMode.SUPERVISOR],
        )

        assert config.enable_planning_tools is True
        assert CollaborationMode.SUPERVISOR in config.collaboration_modes
        print("✅ HarnessConfig creation test passed")

    def test_collaboration_modes(self):
        """测试协作模式枚举"""
        from packages.agent.harness.config import CollaborationMode

        assert CollaborationMode.SUPERVISOR == "supervisor"
        assert CollaborationMode.ROUND_ROBIN == "round_robin"
        assert CollaborationMode.VOTING == "voting"
        assert CollaborationMode.PIPELINE == "pipeline"
        assert CollaborationMode.PARALLEL == "parallel"
        print("✅ Collaboration modes test passed")


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Harness 架构测试")
    print("=" * 60)
    print()

    # Runtime 测试
    print("--- Runtime 层测试 ---")
    test_runtime = TestRuntime()
    test_runtime.test_runtime_config_creation()
    test_runtime.test_agent_runtime_creation()
    asyncio.run(test_runtime.test_simple_graph_execution())
    print()

    # TAO Graph 测试
    print("--- TAO Graph 测试 ---")
    test_tao = TestTAOGraph()
    test_tao.test_tao_state_definition()
    test_tao.test_should_act_router()
    print()

    # Governance 测试
    print("--- Governance 测试 ---")
    test_gov = TestGovernance()
    test_gov.test_governance_engine_creation()
    test_gov.test_trace_lifecycle()
    test_gov.test_callback_handler_creation()
    print()

    # Harness 层测试
    print("--- Harness 层测试 ---")
    test_harness = TestHarness()
    test_harness.test_harness_config_creation()
    test_harness.test_collaboration_modes()
    print()

    print("=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)
