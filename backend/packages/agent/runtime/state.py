"""
标准化 Harness State - 所有子系统的共享数据通道

使用 TypedDict 定义，LangGraph 可以正确处理。
"""
from typing import TypedDict, Annotated, Any, Optional, List
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class HarnessState(TypedDict):
    """
    标准化 Harness State

    字段说明:
    - messages: 对话历史 (LangGraph 自动合并)
    - reasoning: 当前推理过程
    - tool_calls: 待执行的工具调用
    - tool_results: 工具执行结果缓存
    - agents_used: 已使用的 Agent 列表
    - current_agent: 当前执行的 Agent
    - context: 业务上下文 (用户 ID/会话 ID/租户等)
    - metadata: 追踪元数据 (run_id/trace_id 等)
    - iteration: 循环计数
    - should_end: 是否终止
    - termination_reason: 终止原因
    - final_output: 最终输出
    - governance_result: 输出治理结果
    """
    messages: Annotated[List[BaseMessage], add_messages]
    reasoning: str
    tool_calls: list
    tool_results: list
    agents_used: list[str]
    current_agent: str
    context: dict[str, Any]
    metadata: dict[str, Any]
    iteration: int
    should_end: bool
    termination_reason: Optional[str]
    final_output: str
    governance_result: dict


# 兼容旧代码 - TAOState 是 HarnessState 的别名
TAOState = HarnessState
