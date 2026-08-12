"""
标准化 Harness State - 所有子系统的共享数据通道

使用 TypedDict 定义，LangGraph 可以正确处理。
定义原子 reducer 与状态工具函数，供图节点复用。
"""
import re
from typing import Any, Dict, List, Optional, TypedDict, Union, Annotated

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


def append_lists(
    existing: Optional[List[Any]],
    updates: Optional[List[Any]],
) -> List[Any]:
    """用并集合并列表字段（todos/plan/files），避免覆盖旧条目。

    LangGraph 所有消息级 reducer 都必须满足 (old, new) -> merged 签名。
    """
    base = list(existing or [])
    for item in updates or []:
        if item not in base:
            base.append(item)
    return base


def append_string(
    existing: Optional[str],
    updates: Optional[str],
) -> Optional[str]:
    """拼接字符串字段（如 summary 追加）。"""
    if not updates:
        return existing
    if existing:
        return f"{existing}\n{updates}"
    return updates


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
    - todos: 任务清单 (Agent 输出 [TASK] 提取而来)
    - plan: 执行计划步骤
    - files: 涉及的文件列表
    - summary: 上下文摘要 (压缩时拼接)
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
    todos: Annotated[List[Dict[str, Any]], append_lists]
    plan: Annotated[List[str], append_lists]
    files: Annotated[List[Dict[str, Any]], append_lists]
    summary: Annotated[Optional[str], append_string]
    iteration: int
    should_end: bool
    termination_reason: Optional[str]
    final_output: str
    governance_result: dict


# 兼容旧代码 - TAOState 是 HarnessState 的别名
TAOState = HarnessState


_TASK_PATTERN = re.compile(r"\[TASK\]:?\s*(.*?)(?:\n|$)")


def extract_tasks(text: str) -> List[str]:
    """从 LLM 输出中提取任务清单（支持 [TASK]xxx 标记与 Markdown 任务项）。"""
    tasks: List[str] = []
    if not text:
        return tasks

    # 1. [TASK] / [TASK]: 显式标记
    matches = _TASK_PATTERN.findall(text)
    tasks.extend(t.strip() for t in matches if t.strip())

    # 2. Markdown "- [ ]" 任务项
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s*\[[ xX]\]\s+(.+)$", line)
        if m and m.group(1).strip():
            task = m.group(1).strip()
            if task not in tasks:
                tasks.append(task)

    return tasks


def update_todos_from_message(
    state: Dict[str, Any],
    content: Any,
) -> Dict[str, Any]:
    """从消息内容提取任务并合并进 state.todos。

    原子函数，供 think 节点复用；返回新的 state 更新字典。
    """
    text = content if isinstance(content, str) else str(content)
    extracted = extract_tasks(text)
    if not extracted:
        return {}

    todos = list(state.get("todos") or [])
    existing_desc = {t.get("description") for t in todos}
    for desc in extracted:
        if desc not in existing_desc:
            todos.append({"description": desc, "status": "pending"})
            existing_desc.add(desc)

    return {"todos": todos}
