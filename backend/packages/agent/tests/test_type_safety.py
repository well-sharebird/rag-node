"""
类型安全测试

测试事件类型定义和验证
"""
import pytest
from datetime import datetime

from packages.agent.schemas.events import (
    AgentEventType,
    TurnStartEvent,
    TurnEndEvent,
    MessageCreatedEvent,
    ThinkStartEvent,
    ThinkEndEvent,
    ToolCallStartEvent,
    ToolResultEvent,
    ErrorOccurredEvent,
    create_event,
    validate_event,
)


class TestEventTypes:
    """测试事件类型定义"""
    
    def test_turn_start_event(self):
        """测试轮次开始事件"""
        event = TurnStartEvent(
            turn=1,
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        assert event.event_type == "turn_start"
        assert event.turn == 1
        assert len(event.messages) == 1
    
    def test_message_created_event(self):
        """测试消息创建事件"""
        event = MessageCreatedEvent(
            role="user",
            content="Hello World",
            content_type="text",
            metadata={"source": "web"},
        )
        
        assert event.event_type == "message_created"
        assert event.role == "user"
        assert event.content == "Hello World"
        assert event.content_type == "text"
    
    def test_think_cycle_events(self):
        """测试思考周期事件"""
        start_event = ThinkStartEvent(
            iteration=1,
            prompt="Let me think...",
        )
        
        end_event = ThinkEndEvent(
            iteration=1,
            result="The answer is 42",
            reasoning_trace="Step 1: ...\nStep 2: ...",
        )
        
        assert start_event.event_type == "think_start"
        assert start_event.iteration == 1
        assert end_event.event_type == "think_end"
        assert end_event.result == "The answer is 42"
    
    def test_tool_call_events(self):
        """测试工具调用事件"""
        start_event = ToolCallStartEvent(
            tool_call_id="call_123",
            tool_name="calculator",
            arguments={"expression": "2+2"},
        )
        
        result_event = ToolResultEvent(
            tool_call_id="call_123",
            result=4,
            error=None,
        )
        
        assert start_event.event_type == "tool_call_start"
        assert start_event.tool_name == "calculator"
        assert result_event.event_type == "tool_result"
        assert result_event.result == 4
    
    def test_error_event(self):
        """测试错误事件"""
        event = ErrorOccurredEvent(
            error_message="Something went wrong",
            error_type="ValueError",
            stack_trace="Traceback...",
            context={"user_id": 1, "session_id": "xxx"},
        )
        
        assert event.event_type == "error_occurred"
        assert event.error_message == "Something went wrong"
        assert event.error_type == "ValueError"


class TestEventFactory:
    """测试事件工厂函数"""
    
    def test_create_event_turn_start(self):
        """测试创建轮次开始事件"""
        event = create_event(
            AgentEventType.TURN_START,
            turn=1,
            messages=[],
        )
        
        assert isinstance(event, TurnStartEvent)
        assert event.turn == 1
    
    def test_create_event_message_created(self):
        """测试创建消息创建事件"""
        event = create_event(
            AgentEventType.MESSAGE_CREATED,
            role="assistant",
            content="Hi!",
        )
        
        assert isinstance(event, MessageCreatedEvent)
        assert event.role == "assistant"
    
    def test_create_event_invalid_type(self):
        """测试无效事件类型"""
        with pytest.raises(ValueError):
            create_event("invalid_type", foo="bar")


class TestEventValidation:
    """测试事件验证"""
    
    def test_validate_valid_event(self):
        """测试验证有效事件"""
        event_data = {
            "event_type": "turn_start",
            "turn": 1,
            "messages": [],
        }
        
        event = validate_event(event_data)
        assert isinstance(event, TurnStartEvent)
        assert event.turn == 1
    
    def test_validate_invalid_event_type(self):
        """测试验证无效事件类型"""
        event_data = {
            "event_type": "nonexistent_event",
        }
        
        with pytest.raises(ValueError) as exc_info:
            validate_event(event_data)
        
        assert "Invalid event type" in str(exc_info.value)
    
    def test_validate_missing_required_fields(self):
        """测试验证缺少必填字段"""
        # TurnStartEvent 需要 turn 字段
        event_data = {
            "event_type": "turn_start",
            # missing "turn"
        }
        
        with pytest.raises(Exception):  # Pydantic 会抛出 ValidationError
            validate_event(event_data)


class TestEventSerialization:
    """测试事件序列化"""
    
    def test_event_model_dump(self):
        """测试事件模型转字典"""
        event = TurnStartEvent(
            turn=1,
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        data = event.model_dump()
        assert data["event_type"] == "turn_start"
        assert data["turn"] == 1
        assert len(data["messages"]) == 1
    
    def test_event_model_dump_json(self):
        """测试事件序列化为 JSON"""
        event = MessageCreatedEvent(
            role="user",
            content="Hello",
        )
        
        json_str = event.model_dump_json()
        assert "Hello" in json_str
        assert "user" in json_str
    
    def test_event_from_json(self):
        """测试从 JSON 反序列化事件"""
        json_str = '{"event_type": "turn_start", "turn": 5, "messages": []}'
        
        event = TurnStartEvent.model_validate_json(json_str)
        assert event.turn == 5
        assert event.event_type == "turn_start"


class TestEventUnionTypes:
    """测试联合类型"""
    
    def test_turn_event_union(self):
        """测试轮次事件联合类型"""
        from packages.agent.schemas.events import TurnEvent
        
        start: TurnEvent = TurnStartEvent(turn=1, messages=[])
        end: TurnEvent = TurnEndEvent(turn=1)
        
        assert start.event_type == "turn_start"
        assert end.event_type == "turn_end"
    
    def test_message_event_union(self):
        """测试消息事件联合类型"""
        from packages.agent.schemas.events import MessageEvent
        
        created: MessageEvent = MessageCreatedEvent(role="user", content="Hi")
        
        assert created.event_type == "message_created"
    
    def test_tool_event_union(self):
        """测试工具事件联合类型"""
        from packages.agent.schemas.events import ToolEvent
        
        result: ToolEvent = ToolResultEvent(
            tool_call_id="call_1",
            result={"data": "test"},
        )
        
        assert result.event_type == "tool_result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
