"""
Agent Integration Package

将 Phase 1-5 的优化系统集成到执行链路中
装饰器模式：ExecutionOrchestrator 包装 Orchestrator
"""

from packages.agent.integration.execution_chain import (
    ExecutionOrchestrator,
    EventServiceProvider,
    create_execution_orchestrator,
)

__all__ = [
    "ExecutionOrchestrator",
    "EventServiceProvider",
    "create_execution_orchestrator",
]
