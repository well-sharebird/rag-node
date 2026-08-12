"""Harness 核心层 - 生产治理管控（设计文档 2）

五大核心子系统：
1. 上下文工程 - context/
2. 工具治理 - 见 middlewares/ + sandbox/
3. 状态与任务调度 - 见 runtime/state.py
4. 子 Agent 编排 - 见 orchestrator/
5. 验证与可观测 - 见 output/

两大安全重点：
1. 沙箱隔离 - 见 sandbox/
2. 权限护栏 - 见 runtime_engine/permission.py
"""
from packages.agent.core.harness.context import PromptManager, PromptLayer, ContextAssembler, TokenBudgetManager

__all__ = [
    "PromptManager",
    "PromptLayer",
    "ContextAssembler",
    "TokenBudgetManager",
]
