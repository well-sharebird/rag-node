"""上下文工程子系统 - Harness 核心能力（设计文档 2.1）

统一管理所有 Agent 的"人格、规则、上下文、Token 预算"：
- 分层提示管理：SOUL（人格/底线）+ CLAUDE（任务规则/工作流）
- 动态 Agent 配置加载（本地默认 + 数据库垂直 Agent）
- 上下文压缩、去重、污染检测、窗口管理
- Token 预算、限流、防溢出

对接关系：
- LangChain：消费 PromptTemplate、Memory
- LangGraph：每次节点执行前由 Harness 组装合法上下文注入 State
"""
from packages.agent.core.harness.context.prompt_manager import PromptManager, PromptLayer
from packages.agent.core.harness.context.context_assembler import ContextAssembler
from packages.agent.core.harness.context.token_budget import TokenBudgetManager
from packages.agent.core.harness.context.prompt_assembler import PromptAssembler

__all__ = [
    "PromptManager",
    "PromptLayer",
    "ContextAssembler",
    "TokenBudgetManager",
    "PromptAssembler",
]
