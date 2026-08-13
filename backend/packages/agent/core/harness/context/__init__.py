"""上下文工程子系统 - Harness 核心能力（设计文档 2.1）

统一管理所有 Agent 的"人格、规则、上下文、Token 预算"：
- 分层提示管理：SOUL（人格/底线）+ CLAUDE（任务规则/工作流）
- 上下文压缩、去重、污染检测、窗口管理
- Token 预算、限流、防溢出

对接关系：
- LangChain：消费 PromptTemplate、Memory
- LangGraph：每次节点执行前由 Harness 组装合法上下文注入 State（think 节点消费）

当前保留实际装配的：
- `PromptAssembler`（SOUL/CLAUDE 分层组装 + Token 预算裁剪）
- `ContextCompressor`（多轮历史上下文压缩，超预算裁剪旧消息）
"""
from packages.agent.core.harness.context.prompt_assembler import PromptAssembler
from packages.agent.core.harness.context.context_compressor import ContextCompressor

__all__ = ["PromptAssembler", "ContextCompressor"]
