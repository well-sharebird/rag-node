"""
/execute/stream SSE 事件协议 —— 唯一真源（single source of truth）

现状背景：事件 dict 曾由各生产者就地手造（supervisor / tool_executor / api），
无集中 schema、无统一校验，前端靠内联 type 判断背书，改格式极易前后端漂移。
本模块把这些事件收敛成一个 Pydantic 判别联合（AgentStreamEvent）：

- 每个事件一个 model，type 用 Literal 作判别字段
- 工厂函数 ev_xxx() 供生产者调用（类型安全、自文档，取代手造 dict）
- serialize_stream_event() 是后端唯一的 dict→string 掐点，fail-closed 校验

新增一个事件的姿势：
1. 本文件加一个 model（type 用新 Literal）+ 加入 AgentStreamEvent Union + 加 ev_xxx() 工厂
2. 生产者调工厂替代手造
3. 前端 stream-events.ts 的 Union 加一个分支 + 加一个 guard
判别联合天然可扩展，新增类型不改既有 model。
"""
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter


class ToolEventFile(BaseModel):
    """工作空间产物文件（工具执行产生）"""
    filename: str
    relative_path: str


class OrchestratorPlanData(BaseModel):
    """编排决策"""
    need_sub_agents: bool
    run_mode: Literal["serial", "parallel"] = "serial"
    plan: List[dict] = Field(default_factory=list)


class ToolEventData(BaseModel):
    """工具执行生命周期（start/done）"""
    phase: Literal["start", "done"]
    tool: str
    input: dict = Field(default_factory=dict)
    status: Optional[Literal["running", "success", "error", "denied", "limited", "circuit", "blocked"]] = None
    result: Optional[str] = None
    files: List[ToolEventFile] = Field(default_factory=list)
    sandbox: Optional[str] = None


class SubAgentData(BaseModel):
    """子 Agent 生命周期"""
    sub_agent_id: str
    status: Literal["running", "done"]
    success: Optional[bool] = None
    content: Optional[str] = None


class ApprovalRequiredData(BaseModel):
    """HITL 人工审批请求"""
    sub_agent_id: Optional[str] = None
    pending: List[dict] = Field(default_factory=list)


class DoneData(BaseModel):
    """流结束 + 运行验收单（干净停顿语义）"""
    reason: Literal["completed", "max_iterations", "interrupted"] = "completed"
    rounds: int = 0
    tools_used: List[str] = Field(default_factory=list)
    files: List[ToolEventFile] = Field(default_factory=list)


class OrchestratorPlanEvent(BaseModel):
    type: Literal["orchestrator_plan"] = "orchestrator_plan"
    data: OrchestratorPlanData


class ReasoningEvent(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    content: str


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    content: str


class ToolEvent(BaseModel):
    type: Literal["tool_event"] = "tool_event"
    data: ToolEventData


class SubAgentEvent(BaseModel):
    type: Literal["sub_agent"] = "sub_agent"
    data: SubAgentData


class ApprovalRequiredEvent(BaseModel):
    type: Literal["approval_required"] = "approval_required"
    data: Optional[ApprovalRequiredData] = None


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    data: DoneData


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: str
    error_code: Optional[str] = None
    error_category: Optional[str] = None


class CompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    run_id: Optional[str] = None


class CitationsEvent(BaseModel):
    type: Literal["citations"] = "citations"
    citations: List[dict] = Field(default_factory=list)


class AgentSelectedEvent(BaseModel):
    type: Literal["agent_selected"] = "agent_selected"
    agent_name: str


AgentStreamEvent = Annotated[
    Union[
        OrchestratorPlanEvent,
        ReasoningEvent,
        TokenEvent,
        ToolEvent,
        SubAgentEvent,
        ApprovalRequiredEvent,
        DoneEvent,
        ErrorEvent,
        CompleteEvent,
        CitationsEvent,
        AgentSelectedEvent,
    ],
    Field(discriminator="type"),
]


# ============================================================
# 工厂函数 —— 生产者调用，取代手造 dict（全协议唯一构造入口）
# ============================================================

def ev_plan(**kw) -> dict:
    return OrchestratorPlanEvent(data=OrchestratorPlanData(**kw)).model_dump(mode="json")


def ev_reasoning(content: str) -> dict:
    return ReasoningEvent(content=content).model_dump(mode="json")


def ev_token(content: str) -> dict:
    return TokenEvent(content=content).model_dump(mode="json")


def ev_tool(data: dict) -> dict:
    return ToolEvent(data=ToolEventData(**data)).model_dump(mode="json")


def ev_sub_agent(**kw) -> dict:
    return SubAgentEvent(data=SubAgentData(**kw)).model_dump(mode="json")


def ev_approval(**kw) -> dict:
    return ApprovalRequiredEvent(data=ApprovalRequiredData(**kw)).model_dump(mode="json")


def ev_done(**kw) -> dict:
    return DoneEvent(data=DoneData(**kw)).model_dump(mode="json")


def ev_error(error: str, error_code: Optional[str] = None,
             error_category: Optional[str] = None) -> dict:
    return ErrorEvent(error=error, error_code=error_code,
                      error_category=error_category).model_dump(mode="json")


# 仅供前端/其它路径补齐 union，预留工厂（当前 /execute/stream 不产，但 schema 覆盖）
def ev_complete(run_id: Optional[str] = None) -> dict:
    return CompleteEvent(run_id=run_id).model_dump(mode="json")


def ev_citations(citations: list) -> dict:
    return CitationsEvent(citations=citations).model_dump(mode="json")


def ev_agent_selected(agent_name: str) -> dict:
    return AgentSelectedEvent(agent_name=agent_name).model_dump(mode="json")


# ============================================================
# 掐点序列化 —— 后端唯一 dict→string 点，fail-closed 校验
# ============================================================

_STREAM_ADAPTER = TypeAdapter(AgentStreamEvent)


def serialize_stream_event(event, *, fail_closed: bool = True) -> str:
    """把任意事件统一校验并序列化为 JSON 字符串（唯一掐点）。

    fail_closed=True：不匹配协议即抛 ValidationError（由 api 外层 except 捕获产 error 事件）。
    """
    if isinstance(event, str):
        return event
    return _STREAM_ADAPTER.validate_python(event).model_dump_json(exclude_none=True)
