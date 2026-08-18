"""
Event Store 事件存储库

提供事件溯源的高级抽象：
- Session 事件流管理
- 状态重建
- 时间旅行
- 会话 Fork
"""
import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy.orm import Session as SQLAlchemySession

from packages.agent.models.event import AgentEvent, AgentEventType, AgentEventStream
from packages.agent.models.session import AgentSession


class EventStore:
    """
    事件存储库
    
    封装事件溯源的核心操作
    """
    
    def __init__(self, db_session: SQLAlchemySession):
        self.db = db_session
        self._stream = AgentEventStream(db_session)
    
    # ========== 事件追加 ==========
    
    def append_turn_start(
        self,
        session_id: str,
        turn: int,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录轮次开始"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.TURN_START,
            payload={"turn": turn},
            source="system",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_turn_end(
        self,
        session_id: str,
        turn: int,
        result: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录轮次结束"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.TURN_END,
            payload={"turn": turn, "result": result or {}},
            source="system",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_message_created(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录消息创建"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.MESSAGE_CREATED,
            payload={
                "role": role,
                "content": content,
                "metadata": metadata or {},
            },
            source="user" if role == "user" else "agent",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_think_start(
        self,
        session_id: str,
        iteration: int,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录思考开始"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.THINK_START,
            payload={"iteration": iteration},
            source="agent",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_think_end(
        self,
        session_id: str,
        iteration: int,
        result: str,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录思考结束"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.THINK_END,
            payload={"iteration": iteration, "result": result},
            source="agent",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_think_token(
        self,
        session_id: str,
        token: str,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录思考 token（流式）"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.THINK_TOKEN,
            payload={"token": token},
            source="agent",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_tool_call_start(
        self,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录工具调用开始"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.TOOL_CALL_START,
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "arguments": arguments,
            },
            source="agent",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_tool_call_end(
        self,
        session_id: str,
        tool_call_id: str,
        result: Any,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录工具调用结束"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.TOOL_CALL_END,
            payload={
                "tool_call_id": tool_call_id,
                "result": result,
            },
            source="tool",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_tool_result(
        self,
        session_id: str,
        tool_call_id: str,
        result: Any,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录工具结果"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.TOOL_RESULT,
            payload={
                "tool_call_id": tool_call_id,
                "result": result,
            },
            source="tool",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    def append_error(
        self,
        session_id: str,
        error_message: str,
        error_type: str,
        stack_trace: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> AgentEvent:
        """记录错误发生"""
        return self._stream.append(
            session_id=session_id,
            event_type=AgentEventType.ERROR_OCCURRED,
            payload={
                "error_message": error_message,
                "error_type": error_type,
                "stack_trace": stack_trace,
            },
            source="system",
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
    
    # ========== 状态重建 ==========
    
    def rebuild_state(
        self,
        session_id: str,
        up_to_seq: Optional[int] = None,
    ) -> dict:
        """
        从事件重建会话状态
        
        Args:
            session_id: 会话 ID
            up_to_seq: 重建到的序列号（时间旅行）
            
        Returns:
            重建的状态字典
        """
        return self._stream.fold(
            session_id=session_id,
            initial_state={
                "session_id": session_id,
                "messages": [],
                "tool_calls": [],
                "turns": [],
                "errors": [],
            },
        )
    
    def get_messages(
        self,
        session_id: str,
        up_to_seq: Optional[int] = None,
    ) -> list[dict]:
        """
        从事件派生消息列表
        
        Args:
            session_id: 会话 ID
            up_to_seq: 派生到的序列号
            
        Returns:
            消息列表，格式与 OpenAI API 兼容
        """
        state = self.rebuild_state(session_id, up_to_seq)
        return state.get("messages", [])
    
    # ========== 时间旅行 ==========
    
    def time_travel(
        self,
        session_id: str,
        to_seq: int,
    ) -> dict:
        """
        时间旅行到指定序列号的状态
        
        Args:
            session_id: 会话 ID
            to_seq: 目标序列号
            
        Returns:
            历史状态
        """
        return self.rebuild_state(session_id, up_to_seq=to_seq)
    
    def get_event_at(
        self,
        session_id: str,
        seq: int,
    ) -> Optional[AgentEvent]:
        """获取指定序列号的事件"""
        return (
            self.db.query(AgentEvent)
            .filter(
                AgentEvent.session_id == session_id,
                AgentEvent.seq == seq,
            )
            .first()
        )
    
    # ========== 会话 Fork ==========
    
    def fork_session(
        self,
        source_session_id: str,
        new_session: AgentSession,
        from_seq: int = 0,
    ) -> "EventStore":
        """
        Fork 会话到指定事件点
        
        Args:
            source_session_id: 源会话 ID
            new_session: 新会话对象
            from_seq: 从哪个序列号开始复制（0 表示从头开始）
            
        Returns:
            新会话的 EventStore 实例
        """
        # 复制事件
        source_events = self._stream.slice(
            session_id=source_session_id,
            from_seq=from_seq,
        )
        
        for source_event in source_events:
            new_event = AgentEvent(
                session_id=new_session.id,
                seq=source_event.seq - from_seq,  # 重新编号
                event_type=source_event.event_type,
                payload=source_event.payload,
                source=source_event.source,
                correlation_id=source_event.correlation_id,
                causation_id=source_event.causation_id,
            )
            self.db.add(new_event)
        
        self.db.flush()
        return EventStore(self.db)
    
    # ========== 查询 ==========
    
    def get_events(
        self,
        session_id: str,
        event_types: Optional[list[AgentEventType]] = None,
        from_seq: Optional[int] = None,
        to_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[AgentEvent]:
        """
        查询事件
        
        Args:
            session_id: 会话 ID
            event_types: 事件类型过滤
            from_seq: 起始序列号
            to_seq: 结束序列号
            limit: 数量限制
            
        Returns:
            事件列表
        """
        query = (
            self.db.query(AgentEvent)
            .filter(AgentEvent.session_id == session_id)
            .order_by(AgentEvent.seq.asc())
        )
        
        if event_types:
            query = query.filter(
                AgentEvent.event_type.in_([et.value for et in event_types])
            )
        
        if from_seq is not None:
            query = query.filter(AgentEvent.seq >= from_seq)
        
        if to_seq is not None:
            query = query.filter(AgentEvent.seq <= to_seq)
        
        if limit is not None:
            query = query.limit(limit)
        
        return query.all()
    
    def get_latest_seq(self, session_id: str) -> int:
        """获取最新序列号"""
        return self._stream.get_next_seq(session_id) - 1
    
    def get_events_by_correlation(
        self,
        correlation_id: str,
    ) -> list[AgentEvent]:
        """通过关联 ID 查询事件链"""
        return self._stream.get_events_by_correlation(correlation_id)
