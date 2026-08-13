"""
Harness 架构测试

验证统一运行时（OrchestratorRuntime）与 TAO 图正常工作
"""
import pytest
from packages.agent.core.harness.config import RuntimeConfig


# ============================================================
# Test 1: Runtime 配置测试
# ============================================================

class TestRuntime:
    """Runtime 配置测试"""

    def test_runtime_config_creation(self):
        """测试 RuntimeConfig 创建"""
        config = RuntimeConfig(
            stream=True,
            timeout_seconds=300,
            token_budget=4096,
        )

        assert config.stream is True
        assert config.timeout_seconds == 300
        assert config.token_budget == 4096
        print("✅ RuntimeConfig creation test passed")


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
# Test 4: Harness 层测试
# ============================================================

class TestHarness:
    """Harness 层测试"""

    def test_harness_config_creation(self):
        """测试 HarnessConfig 创建"""
        from packages.agent.core.harness.config import HarnessConfig, CollaborationMode

        config = HarnessConfig(
            enable_planning_tools=True,
            collaboration_modes=[CollaborationMode.SUPERVISOR],
        )

        assert config.enable_planning_tools is True
        assert CollaborationMode.SUPERVISOR in config.collaboration_modes
        print("✅ HarnessConfig creation test passed")

    def test_collaboration_modes(self):
        """测试协作模式枚举"""
        from packages.agent.core.harness.config import CollaborationMode

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
    print("--- Runtime 配置测试 ---")
    test_runtime = TestRuntime()
    test_runtime.test_runtime_config_creation()
    print()

    # TAO Graph 测试
    print("--- TAO Graph 测试 ---")
    test_tao = TestTAOGraph()
    test_tao.test_tao_state_definition()
    test_tao.test_should_act_router()
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
