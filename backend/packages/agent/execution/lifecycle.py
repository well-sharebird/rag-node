"""生命周期管理：Agent 状态机 / 会话 fork / 并发 Agent（P2）。

参考 DeepSeek Harness：
- **AgentState**：Agent 状态机（idle/running/paused/failed/disposed），与发送队列。
- **SessionManager.fork**：从某会话边界分叉出新会话（基于事件溯源日志）。
- **AgentRegistry**：管理多个并发 Agent。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    DISPOSED = "disposed"


class AgentState:
    """Agent 状态机 + 发送队列（agent.send 支持）。"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.status = AgentStatus.IDLE
        self.current_turn: Optional[str] = None
        self.inbox: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._turn_seq = 0
        self._disposed = False

    @property
    def is_idle(self) -> bool:
        return self.status == AgentStatus.IDLE

    @property
    def is_running(self) -> bool:
        return self.status == AgentStatus.RUNNING

    def begin_turn(self) -> str:
        if self.status == AgentStatus.DISPOSED:
            raise RuntimeError(f"Agent {self.agent_id} disposed")
        if self.status not in (AgentStatus.IDLE, AgentStatus.PAUSED):
            raise RuntimeError(f"Agent {self.agent_id} already {self.status}")
        self.status = AgentStatus.RUNNING
        self._turn_seq += 1
        self.current_turn = f"{self.agent_id}:turn:{self._turn_seq}"
        return self.current_turn

    def end_turn(self, failed: bool = False) -> None:
        if failed:
            self.status = AgentStatus.FAILED
        else:
            self.status = AgentStatus.IDLE
        self.current_turn = None

    def cancel(self, cause: str = "") -> None:
        if self.status == AgentStatus.RUNNING:
            self.status = AgentStatus.IDLE
            self.current_turn = None
            logger.info("[AgentState] %s cancelled: %s", self.agent_id, cause)

    def send(self, payload: Dict[str, Any]) -> None:
        """向 Agent 发送消息（无需其空闲）。"""
        self.inbox.put_nowait(payload)

    def pause(self) -> None:
        if self.status == AgentStatus.RUNNING:
            self.status = AgentStatus.PAUSED

    def resume(self) -> None:
        if self.status == AgentStatus.PAUSED:
            self.status = AgentStatus.RUNNING

    def dispose(self) -> None:
        self.status = AgentStatus.DISPOSED
        self._disposed = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "current_turn": self.current_turn,
            "inbox_size": self.inbox.qsize(),
        }


class AgentRegistry:
    """并发 Agent 注册表（P2）。"""

    def __init__(self):
        self._agents: Dict[str, AgentState] = {}

    def list(self) -> Dict[str, AgentState]:
        return dict(self._agents)

    def get(self, agent_id: str) -> Optional[AgentState]:
        return self._agents.get(agent_id)

    def create(self, agent_id: Optional[str] = None) -> AgentState:
        agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id} already exists")
        agent = AgentState(agent_id)
        self._agents[agent_id] = agent
        return agent

    def dispose(self, agent_id: str) -> None:
        agent = self._agents.pop(agent_id, None)
        if agent:
            agent.dispose()

    def dispose_all(self) -> None:
        for agent in self._agents.values():
            agent.dispose()
        self._agents.clear()


class SessionManager:
    """会话管理：fork / resume（基于事件溯源日志）。"""

    def __init__(self, log):
        self._log = log
        self._children: Dict[str, str] = {}

    async def fork(self, source_session_id: str, boundary_step: Optional[int] = None,
                   child_session_id: Optional[str] = None) -> str:
        """从源会话分叉出新会话（复制到边界为止的事件）。"""
        events = await self._log.events(source_session_id)
        boundary = events
        if boundary_step is not None:
            boundary = [e for e in events if (e.get("step") or 0) <= boundary_step]
        child_id = child_session_id or f"{source_session_id}:fork:{uuid.uuid4().hex[:4]}"
        for e in boundary:
            await self._log.append(
                child_id, e["event_type"], e["payload"], e["turn"], e.get("step"))
        self._children[child_id] = source_session_id
        return child_id

    async def resume(self, session_id: str) -> List[Dict[str, str]]:
        """恢复会话：返回可灌入模型的推导消息历史。"""
        return await self._log.derive_messages(session_id)

    def parent(self, session_id: str) -> Optional[str]:
        return self._children.get(session_id)
