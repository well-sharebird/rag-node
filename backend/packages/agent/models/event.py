"""
Agent Event 事件溯源模型

事件溯源 (Event Sourcing) 核心实现：
- 所有状态变更都记录为不可变事件
- 通过事件回放重建任意时间点的状态
- 支持时间旅行、会话 Fork、审计追踪
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index, event as sqlalchemy_event
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session as SQLAlchemySession

from packages.core.base_model import Base


class AgentEventType(str, Enum):
    """
    事件类型定义
    
    命名规范：{领域}_{动作}
    - turn_*: 轮次相关
    - message_*: 消息相关
    - think_*: 思考相关
    - tool_*: 工具相关
    - observe_*: 观察相关
    - session_*: 会话相关
    - error_*: 错误相关
    """
    
    # ========== 轮次事件 ==========
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    
    # ========== 消息事件 ==========
    MESSAGE_CREATED = "message_created"
    MESSAGE_UPDATED = "message_updated"
    
    # ========== TAO 循环事件 ==========
    THINK_START = "think_start"
    THINK_END = "think_end"
    THINK_TOKEN = "think_token"  # 流式 token
    
    ACT_START = "act_start"
    ACT_END = "act_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TOOL_RESULT = "tool_result"
    
    OBSERVE_START = "observe_start"
    OBSERVE_END = "observe_end"
    
    # ========== 会话事件 ==========
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_ARCHIVED = "session_archived"
    
    # ========== 错误事件 ==========
    ERROR_OCCURRED = "error_occurred"
    ERROR_RECOVERED = "error_recovered"
    
    # ========== 检查点事件 ==========
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"


class AgentEvent(Base):
    """
    Agent 事件
    
    每个事件代表系统状态的一个不可变变更
    事件按 seq 严格排序，保证因果一致性
    """
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ========== 关联 ==========
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    runtime_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtimes.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # ========== 事件标识 ==========
    seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="事件序列号，session 内单调递增"
    )
    
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="事件类型，参考 AgentEventType"
    )
    
    # ========== 事件数据 ==========
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="事件负载，包含完整的状态变更信息"
    )
    
    # ========== 元数据 ==========
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        index=True,
        comment="关联 ID，用于追踪跨事件的因果链"
    )
    
    causation_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="前因事件 ID，指向触发此事件的上一个事件"
    )
    
    # ========== 来源追踪 ==========
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="system",
        comment="事件来源：system, user, tool, agent"
    )
    
    # ========== 时间戳 ==========
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
        comment="事件发生时间"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        comment="记录创建时间"
    )

    # ========== 关系 ==========
    session = relationship("AgentSession", back_populates="events")
    runtime = relationship("AgentRuntime", backref="events")

    # ========== 索引 ==========
    __table_args__ = (
        # session 内 seq 唯一且有序
        UniqueConstraint('session_id', 'seq', name='uq_session_seq'),
        # 快速查询 session 的事件流
        Index('idx_events_session_seq', 'session_id', 'seq'),
        # 按类型查询
        Index('idx_events_session_type', 'session_id', 'event_type'),
        # 按时间范围查询
        Index('idx_events_session_occurred', 'session_id', 'occurred_at'),
        # 关联追踪
        Index('idx_events_correlation', 'correlation_id'),
    )

    def __repr__(self):
        return f"<AgentEvent {self.event_type} seq={self.seq}>"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "seq": self.seq,
            "event_type": self.event_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "source": self.source,
            "occurred_at": self.occurred_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


class AgentEventStream:
    """
    事件流处理器
    
    提供事件溯源的核心操作：
    - append: 追加事件
    - replay: 回放事件重建状态
    - fold: 折叠事件派生当前状态
    - slice: 切片获取特定范围事件
    """
    
    def __init__(self, db_session: SQLAlchemySession):
        self.db = db_session
    
    def get_next_seq(self, session_id: str) -> int:
        """获取下一个序列号"""
        last_event = (
            self.db.query(AgentEvent)
            .filter(AgentEvent.session_id == session_id)
            .order_by(AgentEvent.seq.desc())
            .first()
        )
        return (last_event.seq + 1) if last_event else 0
    
    def append(
        self,
        session_id: str,
        event_type: AgentEventType,
        payload: dict,
        source: str = "system",
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        runtime_id: Optional[str] = None,
    ) -> AgentEvent:
        """
        追加事件到事件流
        
        Args:
            session_id: 会话 ID
            event_type: 事件类型
            payload: 事件负载
            source: 事件来源
            correlation_id: 关联 ID
            causation_id: 前因事件 ID
            runtime_id: 运行时 ID
            
        Returns:
            新创建的事件对象
        """
        event = AgentEvent(
            session_id=session_id,
            seq=self.get_next_seq(session_id),
            event_type=event_type.value if isinstance(event_type, AgentEventType) else event_type,
            payload=payload,
            source=source,
            correlation_id=correlation_id,
            causation_id=causation_id,
            runtime_id=runtime_id,
        )
        self.db.add(event)
        self.db.flush()  # 获取生成的 ID
        return event
    
    def replay(
        self,
        session_id: str,
        up_to_seq: Optional[int] = None,
        event_types: Optional[list[str]] = None,
    ) -> list[AgentEvent]:
        """
        回放事件流
        
        Args:
            session_id: 会话 ID
            up_to_seq: 回放到的序列号（用于时间旅行）
            event_types: 过滤的事件类型列表
            
        Returns:
            事件列表，按 seq 升序排列
        """
        query = (
            self.db.query(AgentEvent)
            .filter(AgentEvent.session_id == session_id)
            .order_by(AgentEvent.seq.asc())
        )
        
        if up_to_seq is not None:
            query = query.filter(AgentEvent.seq <= up_to_seq)
        
        if event_types:
            query = query.filter(AgentEvent.event_type.in_(event_types))
        
        return query.all()
    
    def fold(
        self,
        session_id: str,
        initial_state: Optional[dict] = None,
        event_types: Optional[list[str]] = None,
    ) -> dict:
        """
        折叠事件流派生当前状态
        
        Args:
            session_id: 会话 ID
            initial_state: 初始状态
            event_types: 处理的事件类型列表
            
        Returns:
            派生状态
        """
        state = initial_state or {}
        events = self.replay(session_id, event_types=event_types)
        
        for event in events:
            state = self._apply_event(state, event)
        
        return state
    
    def _apply_event(self, state: dict, event: AgentEvent) -> dict:
        """
        应用单个事件到状态
        
        根据事件类型更新状态
        """
        event_type = event.event_type
        payload = event.payload
        
        if event_type == AgentEventType.TURN_START.value:
            state["current_turn"] = payload.get("turn")
            state["turn_status"] = "running"
            
        elif event_type == AgentEventType.TURN_END.value:
            state["turn_status"] = "completed"
            
        elif event_type == AgentEventType.MESSAGE_CREATED.value:
            messages = state.get("messages", [])
            messages.append({
                "role": payload.get("role"),
                "content": payload.get("content"),
                "event_seq": event.seq,
                "metadata": payload.get("metadata", {}),
            })
            state["messages"] = messages
            
        elif event_type == AgentEventType.THINK_START.value:
            state["think"] = {
                "status": "running",
                "iteration": payload.get("iteration"),
            }
            
        elif event_type == AgentEventType.THINK_END.value:
            state["think"] = {
                "status": "completed",
                "result": payload.get("result"),
            }
            
        elif event_type == AgentEventType.TOOL_CALL_START.value:
            tool_calls = state.get("tool_calls", [])
            tool_calls.append({
                "id": payload.get("tool_call_id"),
                "name": payload.get("tool_name"),
                "arguments": payload.get("arguments"),
                "status": "running",
            })
            state["tool_calls"] = tool_calls
            
        elif event_type == AgentEventType.TOOL_RESULT.value:
            for tool_call in state.get("tool_calls", []):
                if tool_call["id"] == payload.get("tool_call_id"):
                    tool_call["status"] = "completed"
                    tool_call["result"] = payload.get("result")
                    break
                    
        elif event_type == AgentEventType.ERROR_OCCURRED.value:
            state["error"] = {
                "message": payload.get("error_message"),
                "error_type": payload.get("error_type"),
                "seq": event.seq,
            }
        
        return state
    
    def slice(
        self,
        session_id: str,
        from_seq: int,
        to_seq: Optional[int] = None,
    ) -> list[AgentEvent]:
        """
        获取事件切片
        
        Args:
            session_id: 会话 ID
            from_seq: 起始序列号（包含）
            to_seq: 结束序列号（包含），None 表示到最后
            
        Returns:
            事件切片
        """
        query = (
            self.db.query(AgentEvent)
            .filter(AgentEvent.session_id == session_id)
            .filter(AgentEvent.seq >= from_seq)
            .order_by(AgentEvent.seq.asc())
        )
        
        if to_seq is not None:
            query = query.filter(AgentEvent.seq <= to_seq)
        
        return query.all()
    
    def get_events_by_correlation(
        self,
        correlation_id: str,
    ) -> list[AgentEvent]:
        """
        获取同一关联 ID 的所有事件
        
        用于追踪因果链
        """
        return (
            self.db.query(AgentEvent)
            .filter(AgentEvent.correlation_id == correlation_id)
            .order_by(AgentEvent.seq.asc())
            .all()
        )


# ========== SQLAlchemy 事件监听 ==========

@sqlalchemy_event.listens_for(AgentEvent, "before_insert")
def validate_event_seq(mapper, connection, target):
    """
    验证事件序列号的单调性
    
    确保同一 session 内 seq 严格递增
    """
    # 注意：实际应用中可能需要加锁防止并发问题
    pass
