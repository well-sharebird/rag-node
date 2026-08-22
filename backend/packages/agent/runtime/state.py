"""
Agent 状态定义

统一状态管理，包含：
- messages: 对话消息列表
- 沙箱信息
- 线程数据
- 工具调用/结果
- 任务列表（计划模式）
- 标题等元数据
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


@dataclass
class ExecutionResult:
    """通用图执行结果（统一运行时 execute/resume 的返回类型）。"""

    success: bool
    result: Optional[Any] = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None
    # 原始异常（供审批 GraphInterrupt 等提取，默认 None 保持后向兼容）
    error: Optional[BaseException] = None

    @classmethod
    def ok(cls, result: Any, duration_ms: int = 0, metadata: Optional[Dict] = None):
        return cls(success=True, result=result, duration_ms=duration_ms, metadata=metadata)

    @classmethod
    def error(cls, error_message: str, duration_ms: int = 0, *,
              error: Optional[BaseException] = None,
              metadata: Optional[Dict] = None):
        return cls(success=False, error_message=error_message, duration_ms=duration_ms,
                   metadata=metadata, error=error)


class AgentState(TypedDict, total=False):
    """
    Agent 状态（参考 DeerFlow ThreadState）
    
    核心字段：
    - messages: 对话消息列表（LangGraph 必需）
    - iteration: 当前迭代次数
    - tool_calls: 工具调用列表
    - tool_results: 工具结果列表
    
    扩展字段（由中间件注入）：
    - sandbox: 沙箱信息
    - thread_data: 线程数据路径
    - title: 对话标题
    - todos: 任务列表
    - artifacts: 生成的文件
    """
    
    # LangGraph 基础字段
    messages: List[Any]
    
    # 迭代控制
    iteration: int
    
    # 工具调用
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    
    # 推理内容（由 think_node 注入）
    reasoning: Optional[str]
    
    # 沙箱环境（由 SandboxMiddleware 注入）
    sandbox: Optional[Dict[str, Any]]
    
    # 线程数据（由 ThreadDataMiddleware 注入）
    thread_data: Optional[Dict[str, str]]
    
    # 元数据
    title: Optional[str]
    
    # 任务列表（计划模式，由 TodoListMiddleware 注入）
    todos: Optional[List[Dict[str, Any]]]
    
    # 生成的文件
    artifacts: Optional[List[str]]
    
    # 上传文件
    uploaded_files: Optional[Dict[str, Any]]
    
    # 视觉模型图像
    viewed_images: Optional[Dict[str, Any]]
    
    # 中间件控制字段
    _force_end: bool
    _end_reason: Optional[str]
    _interrupt: Optional[str]
    _clarification_request: Optional[Dict[str, Any]]
    _needs_title: bool


class OrchestratorState(AgentState, total=False):
    """
    编排器状态（扩展 AgentState）
    
    多 Agent 编排专用字段：
    - sub_tasks: 子任务列表
    - sub_agent_results: 子 Agent 结果
    - final_answer: 最终答案
    - main_agent_config: 主 Agent 配置
    """
    
    # 子任务
    sub_tasks: List[Dict[str, Any]]
    
    # 子 Agent 结果
    sub_agent_results: List[Dict[str, Any]]
    
    # 最终答案
    final_answer: Optional[str]
    
    # 主 Agent 配置
    main_agent_config: Optional[Dict[str, Any]]
    
    # 临时子 Agent 配置
    temp_sub_config: Optional[Dict[str, Any]]
    
    # 会话/追踪
    session_id: Optional[str]
    trace_id: Optional[str]
    
    # 错误信息
    error: Optional[str]


# ============================================================================
# 工具函数（从旧 state 模块迁移）
# ============================================================================

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
            todos.append({
                "description": desc,
                "status": "pending",
            })
    
    return {"todos": todos}
