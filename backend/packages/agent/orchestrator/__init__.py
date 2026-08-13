"""主从编排（Orchestrator）— 主 Agent 编排 + 子垂直 Agent 执行单元

核心范式：主 Agent 作为唯一对外入口，子 Agent 是被调用的能力单元（不直接接用户输入）。
"""
from packages.agent.orchestrator.state import SubTask, SubAgentResult, OrchestratorState
from packages.agent.orchestrator.agent_loader import AgentLoader

__all__ = [
    "SubTask",
    "SubAgentResult",
    "OrchestratorState",
    "AgentLoader",
]
