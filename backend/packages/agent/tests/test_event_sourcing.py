"""
事件溯源系统核心逻辑测试
"""
import pytest
from datetime import datetime
from uuid import uuid4

from packages.agent.models.event import AgentEventType


class SimpleEventStore:
    """简单的事件存储实现（内存版）"""
    
    def __init__(self):
        self.events = []  # List[dict]
    
    def append(self, session_id, event_type, payload, source="system", **kwargs):
        last_seq = max([e["seq"] for e in self.events if e["session_id"] == session_id], default=-1)
        event = {
            "id": str(uuid4()),
            "session_id": session_id,
            "seq": last_seq + 1,
            "event_type": event_type.value if isinstance(event_type, AgentEventType) else event_type,
            "payload": payload,
            "source": source,
            **kwargs
        }
        self.events.append(event)
        return event
    
    def replay(self, session_id, up_to_seq=None, event_types=None):
        events = [e for e in self.events if e["session_id"] == session_id]
        events.sort(key=lambda x: x["seq"])
        
        if up_to_seq is not None:
            events = [e for e in events if e["seq"] <= up_to_seq]
        if event_types:
            events = [e for e in events if e["event_type"] in event_types]
        return events
    
    def fold(self, session_id, initial_state=None, event_types=None):
        state = initial_state or {}
        events = self.replay(session_id, event_types=event_types)
        for event in events:
            state = self._apply_event(state, event)
        return state
    
    def _apply_event(self, state, event):
        # event is always a dict
        event_type = event["event_type"]
        payload = event["payload"]
        
        if event_type == "turn_start":
            state["current_turn"] = payload.get("turn")
            state["turn_status"] = "running"
        elif event_type == "turn_end":
            state["turn_status"] = "completed"
        elif event_type == "message_created":
            messages = state.get("messages", [])
            messages.append({
                "role": payload.get("role"),
                "content": payload.get("content"),
                "event_seq": event["seq"],
            })
            state["messages"] = messages
        elif event_type == "tool_call_start":
            tool_calls = state.get("tool_calls", [])
            tool_calls.append({
                "id": payload.get("tool_call_id"),
                "name": payload.get("tool_name"),
                "status": "running",
            })
            state["tool_calls"] = tool_calls
        elif event_type == "tool_result":
            for tc in state.get("tool_calls", []):
                if tc["id"] == payload.get("tool_call_id"):
                    tc["status"] = "completed"
                    tc["result"] = payload.get("result")
                    break
        elif event_type == "error_occurred":
            state["error"] = {
                "message": payload.get("error_message"),
                "seq": event["seq"],
            }
        return state
    
    def slice(self, session_id, from_seq, to_seq=None):
        events = [e for e in self.events if e["session_id"] == session_id]
        events.sort(key=lambda x: x["seq"])
        
        events = [e for e in events if e["seq"] >= from_seq]
        if to_seq is not None:
            events = [e for e in events if e["seq"] <= to_seq]
        return events
    
    def get_latest_seq(self, session_id):
        seqs = [e["seq"] for e in self.events if e["session_id"] == session_id]
        return max(seqs, default=-1)


@pytest.fixture
def event_store():
    return SimpleEventStore()


class TestEventAppend:
    """测试事件追加"""
    
    def test_append_turn_start(self, event_store):
        session_id = f"session_{uuid4()}"
        event = event_store.append(
            session_id=session_id,
            event_type=AgentEventType.TURN_START,
            payload={"turn": 1},
        )
        assert event["event_type"] == "turn_start"
        assert event["seq"] == 0
        assert event["payload"]["turn"] == 1
    
    def test_append_message_created(self, event_store):
        session_id = f"session_{uuid4()}"
        event = event_store.append(
            session_id=session_id,
            event_type=AgentEventType.MESSAGE_CREATED,
            payload={"role": "user", "content": "Hello"},
        )
        assert event["event_type"] == "message_created"
        assert event["payload"]["role"] == "user"
    
    def test_event_seq_auto_increment(self, event_store):
        session_id = f"session_{uuid4()}"
        event1 = event_store.append(session_id, AgentEventType.TURN_START, {"turn": 1})
        event2 = event_store.append(session_id, AgentEventType.TURN_START, {"turn": 2})
        event3 = event_store.append(session_id, AgentEventType.TURN_START, {"turn": 3})
        
        assert event1["seq"] == 0
        assert event2["seq"] == 1
        assert event3["seq"] == 2


class TestStateRebuild:
    """测试状态重建"""
    
    def test_rebuild_empty_state(self, event_store):
        session_id = f"session_{uuid4()}"
        state = event_store.fold(
            session_id=session_id,
            initial_state={"session_id": session_id, "messages": [], "tool_calls": []},
        )
        assert state["session_id"] == session_id
        assert state["messages"] == []
    
    def test_rebuild_state_with_messages(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "user", "content": "Hello"})
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "assistant", "content": "Hi!"})
        
        state = event_store.fold(
            session_id=session_id,
            initial_state={"messages": []},
        )
        assert len(state["messages"]) == 2
        assert state["messages"][0]["content"] == "Hello"
        assert state["messages"][1]["content"] == "Hi!"
    
    def test_rebuild_state_with_tool_calls(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(
            session_id, AgentEventType.TOOL_CALL_START,
            {"tool_call_id": "call_1", "tool_name": "search"}
        )
        event_store.append(
            session_id, AgentEventType.TOOL_RESULT,
            {"tool_call_id": "call_1", "result": {"results": ["r1", "r2"]}}
        )
        
        state = event_store.fold(
            session_id=session_id,
            initial_state={"tool_calls": []},
        )
        assert len(state["tool_calls"]) == 1
        assert state["tool_calls"][0]["status"] == "completed"
        assert state["tool_calls"][0]["result"] == {"results": ["r1", "r2"]}
    
    def test_rebuild_state_with_turns(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(session_id, AgentEventType.TURN_START, {"turn": 1})
        event_store.append(session_id, AgentEventType.TURN_END, {"turn": 1, "result": {"completed": True}})
        
        state = event_store.fold(
            session_id=session_id,
            initial_state={},
        )
        assert state["current_turn"] == 1
        assert state["turn_status"] == "completed"


class TestTimeTravel:
    """测试时间旅行"""
    
    def test_time_travel_to_specific_seq(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "user", "content": "Msg 1"})
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "assistant", "content": "Msg 2"})
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "user", "content": "Msg 3"})
        
        # 获取前 2 个事件
        events = event_store.replay(session_id, up_to_seq=1)
        assert len(events) == 2
        assert events[0]["payload"]["content"] == "Msg 1"
        assert events[1]["payload"]["content"] == "Msg 2"


class TestEventQuery:
    """测试事件查询"""
    
    def test_get_events_by_type(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(session_id, AgentEventType.TURN_START, {"turn": 1})
        event_store.append(session_id, AgentEventType.MESSAGE_CREATED, {"role": "user", "content": "Hello"})
        event_store.append(session_id, AgentEventType.TURN_END, {"turn": 1})
        
        events = event_store.replay(
            session_id,
            event_types=["turn_start", "turn_end"],
        )
        assert len(events) == 2
    
    def test_get_events_by_range(self, event_store):
        session_id = f"session_{uuid4()}"
        for i in range(10):
            event_store.append(session_id, AgentEventType.TURN_START, {"turn": i})
        
        events = event_store.slice(session_id, from_seq=3, to_seq=6)
        assert len(events) == 4
        assert events[0]["seq"] == 3
        assert events[-1]["seq"] == 6
    
    def test_get_latest_seq(self, event_store):
        session_id = f"session_{uuid4()}"
        event_store.append(session_id, AgentEventType.TURN_START, {"turn": 1})
        event_store.append(session_id, AgentEventType.TURN_START, {"turn": 2})
        event_store.append(session_id, AgentEventType.TURN_START, {"turn": 3})
        
        latest_seq = event_store.get_latest_seq(session_id)
        assert latest_seq == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
