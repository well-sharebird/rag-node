"""
事件类型定义

使用 Pydantic v2 提供精确的类型定义，替代 dict 和 Any
"""
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# ========== 事件类型枚举 ==========

class AgentEventType(str, Enum):
    """事件类型"""
    
    # 轮次
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    
    # 消息
    MESSAGE_CREATED = "message_created"
    MESSAGE_UPDATED = "message_updated"
    
    # TAO 循环
    THINK_START = "think_start"
    THINK_END = "think_end"
    THINK_TOKEN = "think_token"
    
    ACT_START = "act_start"
    ACT_END = "act_end"
    
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TOOL_RESULT = "tool_result"
    
    OBSERVE_START = "observe_start"
    OBSERVE_END = "observe_end"
    
    # 会话
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_ARCHIVED = "session_archived"
    
    # 错误
    ERROR_OCCURRED = "error_occurred"
    ERROR_RECOVERED = "error_recovered"
    
    # 检查点
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"


# ========== 基础事件结构 ==========

class BaseEvent(BaseModel):
    """基础事件"""
    event_type: AgentEventType
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ========== 轮次事件 ==========

class TurnStartEvent(BaseEvent):
    """轮次开始"""
    event_type: Literal[AgentEventType.TURN_START] = AgentEventType.TURN_START
    turn: int = Field(..., description="轮次编号")
    messages: list[dict] = Field(default_factory=list, description="当前消息历史")


class TurnEndEvent(BaseEvent):
    """轮次结束"""
    event_type: Literal[AgentEventType.TURN_END] = AgentEventType.TURN_END
    turn: int = Field(..., description="轮次编号")
    result: Optional[dict] = Field(default=None, description="轮次结果")


# ========== 消息事件 ==========

class MessageCreatedEvent(BaseEvent):
    """消息创建"""
    event_type: Literal[AgentEventType.MESSAGE_CREATED] = AgentEventType.MESSAGE_CREATED
    role: Literal["system", "user", "assistant", "tool"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    content_type: str = Field(default="text", description="内容类型")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    tool_calls: Optional[list[dict]] = Field(default=None, description="工具调用")
    referenced_file_ids: Optional[list[str]] = Field(default=None, description="引用的文件 ID")


class MessageUpdatedEvent(BaseEvent):
    """消息更新"""
    event_type: Literal[AgentEventType.MESSAGE_UPDATED] = AgentEventType.MESSAGE_UPDATED
    message_id: str = Field(..., description="消息 ID")
    updates: dict[str, Any] = Field(..., description="更新内容")


# ========== TAO 循环事件 ==========

class ThinkStartEvent(BaseEvent):
    """思考开始"""
    event_type: Literal[AgentEventType.THINK_START] = AgentEventType.THINK_START
    iteration: int = Field(..., description="迭代次数")
    prompt: Optional[str] = Field(default=None, description="思考提示")


class ThinkEndEvent(BaseEvent):
    """思考结束"""
    event_type: Literal[AgentEventType.THINK_END] = AgentEventType.THINK_END
    iteration: int = Field(..., description="迭代次数")
    result: str = Field(..., description="思考结果")
    reasoning_trace: Optional[str] = Field(default=None, description="推理轨迹")


class ThinkTokenEvent(BaseEvent):
    """思考 token（流式）"""
    event_type: Literal[AgentEventType.THINK_TOKEN] = AgentEventType.THINK_TOKEN
    token: str = Field(..., description="Token 内容")
    position: int = Field(default=0, description="Token 位置")


class ActStartEvent(BaseEvent):
    """行动开始"""
    event_type: Literal[AgentEventType.ACT_START] = AgentEventType.ACT_START
    tool_calls: list[dict] = Field(default_factory=list, description="待调用的工具")


class ActEndEvent(BaseEvent):
    """行动结束"""
    event_type: Literal[AgentEventType.ACT_END] = AgentEventType.ACT_END
    results: list[Any] = Field(default_factory=list, description="工具调用结果")


class ToolCallStartEvent(BaseEvent):
    """工具调用开始"""
    event_type: Literal[AgentEventType.TOOL_CALL_START] = AgentEventType.TOOL_CALL_START
    tool_call_id: str = Field(..., description="工具调用 ID")
    tool_name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(..., description="工具参数")


class ToolCallEndEvent(BaseEvent):
    """工具调用结束"""
    event_type: Literal[AgentEventType.TOOL_CALL_END] = AgentEventType.TOOL_CALL_END
    tool_call_id: str = Field(..., description="工具调用 ID")
    success: bool = Field(..., description="是否成功")


class ToolResultEvent(BaseEvent):
    """工具结果"""
    event_type: Literal[AgentEventType.TOOL_RESULT] = AgentEventType.TOOL_RESULT
    tool_call_id: str = Field(..., description="工具调用 ID")
    result: Any = Field(..., description="工具返回结果")
    error: Optional[str] = Field(default=None, description="错误信息")


class ObserveStartEvent(BaseEvent):
    """观察开始"""
    event_type: Literal[AgentEventType.OBSERVE_START] = AgentEventType.OBSERVE_START
    observations: list[str] = Field(default_factory=list, description="观察结果")


class ObserveEndEvent(BaseEvent):
    """观察结束"""
    event_type: Literal[AgentEventType.OBSERVE_END] = AgentEventType.OBSERVE_END
    summary: str = Field(..., description="观察摘要")


# ========== 会话事件 ==========

class SessionCreatedEvent(BaseEvent):
    """会话创建"""
    event_type: Literal[AgentEventType.SESSION_CREATED] = AgentEventType.SESSION_CREATED
    session_id: str = Field(..., description="会话 ID")
    runtime_id: str = Field(..., description="运行时 ID")
    user_id: int = Field(..., description="用户 ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class SessionUpdatedEvent(BaseEvent):
    """会话更新"""
    event_type: Literal[AgentEventType.SESSION_UPDATED] = AgentEventType.SESSION_UPDATED
    session_id: str = Field(..., description="会话 ID")
    updates: dict[str, Any] = Field(..., description="更新内容")


class SessionArchivedEvent(BaseEvent):
    """会话归档"""
    event_type: Literal[AgentEventType.SESSION_ARCHIVED] = AgentEventType.SESSION_ARCHIVED
    session_id: str = Field(..., description="会话 ID")
    reason: str = Field(default="user_request", description="归档原因")


# ========== 错误事件 ==========

class ErrorOccurredEvent(BaseEvent):
    """错误发生"""
    event_type: Literal[AgentEventType.ERROR_OCCURRED] = AgentEventType.ERROR_OCCURRED
    error_message: str = Field(..., description="错误信息")
    error_type: str = Field(..., description="错误类型")
    stack_trace: Optional[str] = Field(default=None, description="堆栈跟踪")
    context: dict[str, Any] = Field(default_factory=dict, description="错误上下文")


class ErrorRecoveredEvent(BaseEvent):
    """错误恢复"""
    event_type: Literal[AgentEventType.ERROR_RECOVERED] = AgentEventType.ERROR_RECOVERED
    error_message: str = Field(..., description="原始错误信息")
    recovery_action: str = Field(..., description="恢复动作")
    success: bool = Field(..., description="是否恢复成功")


# ========== 检查点事件 ==========

class CheckpointCreatedEvent(BaseEvent):
    """检查点创建"""
    event_type: Literal[AgentEventType.CHECKPOINT_CREATED] = AgentEventType.CHECKPOINT_CREATED
    checkpoint_id: str = Field(..., description="检查点 ID")
    checkpoint_name: str = Field(..., description="检查点名称")
    checkpoint_type: Literal["manual", "auto", "system"] = Field(..., description="检查点类型")
    state_snapshot: dict[str, Any] = Field(..., description="状态快照")


class CheckpointRestoredEvent(BaseEvent):
    """检查点恢复"""
    event_type: Literal[AgentEventType.CHECKPOINT_RESTORED] = AgentEventType.CHECKPOINT_RESTORED
    checkpoint_id: str = Field(..., description="检查点 ID")
    restored_state: dict[str, Any] = Field(..., description="恢复的状态")


# ========== 联合类型 ==========

TurnEvent = Union[TurnStartEvent, TurnEndEvent]
MessageEvent = Union[MessageCreatedEvent, MessageUpdatedEvent]
ThinkEvent = Union[ThinkStartEvent, ThinkEndEvent, ThinkTokenEvent]
ToolEvent = Union[ToolCallStartEvent, ToolCallEndEvent, ToolResultEvent]
ObserveEvent = Union[ObserveStartEvent, ObserveEndEvent]
SessionEvent = Union[SessionCreatedEvent, SessionUpdatedEvent, SessionArchivedEvent]
ErrorEvent = Union[ErrorOccurredEvent, ErrorRecoveredEvent]
CheckpointEvent = Union[CheckpointCreatedEvent, CheckpointRestoredEvent]

# 所有事件类型
AgentEvent = Union[
    TurnEvent,
    MessageEvent,
    ThinkEvent,
    ToolEvent,
    ActStartEvent,
    ActEndEvent,
    ObserveEvent,
    SessionEvent,
    ErrorEvent,
    CheckpointEvent,
]


# ========== 事件映射 ==========

EVENT_TYPE_MAP: dict[AgentEventType, type[BaseEvent]] = {
    AgentEventType.TURN_START: TurnStartEvent,
    AgentEventType.TURN_END: TurnEndEvent,
    AgentEventType.MESSAGE_CREATED: MessageCreatedEvent,
    AgentEventType.MESSAGE_UPDATED: MessageUpdatedEvent,
    AgentEventType.THINK_START: ThinkStartEvent,
    AgentEventType.THINK_END: ThinkEndEvent,
    AgentEventType.THINK_TOKEN: ThinkTokenEvent,
    AgentEventType.ACT_START: ActStartEvent,
    AgentEventType.ACT_END: ActEndEvent,
    AgentEventType.TOOL_CALL_START: ToolCallStartEvent,
    AgentEventType.TOOL_CALL_END: ToolCallEndEvent,
    AgentEventType.TOOL_RESULT: ToolResultEvent,
    AgentEventType.OBSERVE_START: ObserveStartEvent,
    AgentEventType.OBSERVE_END: ObserveEndEvent,
    AgentEventType.SESSION_CREATED: SessionCreatedEvent,
    AgentEventType.SESSION_UPDATED: SessionUpdatedEvent,
    AgentEventType.SESSION_ARCHIVED: SessionArchivedEvent,
    AgentEventType.ERROR_OCCURRED: ErrorOccurredEvent,
    AgentEventType.ERROR_RECOVERED: ErrorRecoveredEvent,
    AgentEventType.CHECKPOINT_CREATED: CheckpointCreatedEvent,
    AgentEventType.CHECKPOINT_RESTORED: CheckpointRestoredEvent,
}


# ========== 辅助函数 ==========

def create_event(event_type: AgentEventType, **kwargs) -> BaseEvent:
    """
    创建类型化的事件
    
    Args:
        event_type: 事件类型
        **kwargs: 事件字段
        
    Returns:
        类型化的事件对象
    """
    event_class = EVENT_TYPE_MAP.get(event_type)
    if not event_class:
        raise ValueError(f"Unknown event type: {event_type}")
    
    return event_class(**kwargs)


def validate_event(event_data: dict) -> BaseEvent:
    """
    验证事件数据
    
    Args:
        event_data: 事件数据字典
        
    Returns:
        类型化的事件对象
    """
    event_type_str = event_data.get("event_type")
    try:
        event_type = AgentEventType(event_type_str)
    except ValueError:
        raise ValueError(f"Invalid event type: {event_type_str}")
    
    # 移除 event_type 避免重复传递
    kwargs = {k: v for k, v in event_data.items() if k != "event_type"}
    return create_event(event_type, **kwargs)
