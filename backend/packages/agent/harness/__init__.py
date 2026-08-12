"""
Harness 层 - 基础方案引擎

执行内核已统一为 OrchestratorRuntime（packages/agent/orchestrator/）。
此处保留 HarnessConfig 等配置，供兼容引用。

历史：HarnessEngine 已并入单一执行内核（OrchestratorRuntime）后删除。
"""
from packages.agent.harness.config import HarnessConfig, CollaborationMode

__all__ = [
    "HarnessConfig",
    "CollaborationMode",
]
