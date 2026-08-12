"""
LangGraph Checkpoint 持久化服务
将 LangGraph 的状态存储到 PostgreSQL，实现用户隔离

注意：LangGraph CheckpointSaver 必须是同步的，因为 LangGraph 内部调用同步方法。
这里使用同步 Session 进行数据库操作。
"""
from __future__ import annotations
import base64
import json
from typing import Any, Iterator, Optional
from datetime import datetime
from uuid import uuid4

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import select, delete, text
from sqlalchemy.orm import Session

from packages.agent.models.agent import AgentMemory

# LangGraph checkpoint 包含 BaseMessage（HumanMessage 等），无法直接 JSON 序列化。
# 用 JsonPlusSerializer（msgpack，支持 LangChain 消息）序列化后 base64 存 JSONB。
_serde = JsonPlusSerializer()


def _ser_bytes(obj: Any) -> str:
    """序列化对象为 base64 字符串（支持 LangChain BaseMessage）。"""
    data = _serde.dumps_typed(obj)[1]
    return base64.b64encode(data).decode()


def _deser_bytes(s: str) -> Any:
    """反序列化 base64 字符串为对象。"""
    try:
        return _serde.loads_typed(("json", base64.b64decode(s)))
    except Exception:
        return _serde.loads_typed(("msgpack", base64.b64decode(s)))


class DatabaseCheckpointSaver(BaseCheckpointSaver):
    """
    将 LangGraph 检查点存储到 PostgreSQL

    使用 thread_id 实现用户隔离：
    - thread_id 格式："{user_id}:{agent_id}:{session_id}"
    - 每个用户的会话状态独立存储
    """

    def __init__(self, sync_db: Session):
        super().__init__()
        self.db = sync_db

    def _parse_thread_id(self, thread_id: str) -> tuple[int, str, str]:
        """解析 thread_id 格式："{user_id}:{agent_id}:{session_id}" """
        parts = thread_id.split(":", 2)
        if len(parts) == 3:
            return int(parts[0]), parts[1], parts[2]
        elif len(parts) == 2:
            return int(parts[0]), parts[1], "default"
        else:
            return 0, thread_id, "default"

    @staticmethod
    def _safe_uuid(value: str) -> Optional[str]:
        """将 agent_id 转为合法 UUID；虚拟代理（如 meta，无 agent_configs 记录）返回 None。

        agent_memories.agent_id 已可为空，NULL 会通过外键 NO ACTION 校验。
        """
        import uuid as _uuid
        if not value:
            return None
        try:
            return str(_uuid.UUID(value))
        except (ValueError, AttributeError):
            return None

    def _get_checkpoint_key(self, config: dict, checkpoint_id: Optional[str] = None) -> str:
        """生成检查点存储键

        Args:
            config: LangGraph config
            checkpoint_id: 如果提供则使用，否则从 config 获取或生成新的
        """
        thread_id = config["configurable"].get("thread_id", "default")
        if checkpoint_id is None:
            checkpoint_id = get_checkpoint_id(config)
        if checkpoint_id is None:
            # 如果没有 checkpoint_id，使用 thread_id 作为键（首次对话）
            return f"checkpoint:{thread_id}:latest"
        return f"checkpoint:{thread_id}:{checkpoint_id}"

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """获取检查点元组"""
        thread_id = config["configurable"].get("thread_id")

        if not thread_id:
            return None

        # 使用 "latest" 键获取最新的 checkpoint
        key = f"checkpoint:{thread_id}:latest"

        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.thread_id == key,
                AgentMemory.memory_type == "checkpoint"
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not memory:
            return None

        checkpoint_data = memory.content.get("checkpoint", {})
        metadata = memory.content.get("metadata", {})
        pending_writes = memory.content.get("pending_writes", [])

        return CheckpointTuple(
            checkpoint=checkpoint_data,
            metadata=metadata,
            pending_writes=pending_writes,
            config=config,
        )

    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_values: dict,
        saved: Optional[dict] = None,
    ) -> dict:
        """保存检查点 - 始终使用 "latest" 键更新最新状态"""
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return {}

        user_id, agent_id, session_id = self._parse_thread_id(thread_id)
        key = f"checkpoint:{thread_id}:latest"

        # 先尝试更新现有的 checkpoint
        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.thread_id == key,
                AgentMemory.memory_type == "checkpoint"
            )
            .limit(1)
        ).scalar_one_or_none()

        if memory:
            # 更新现有的 checkpoint
            memory.content = {
                "checkpoint": checkpoint,
                "metadata": metadata,
                "pending_writes": [],
            }
            memory.updated_at = datetime.utcnow()
        else:
            # 创建新的 checkpoint
            memory = AgentMemory(
                id=str(uuid4()),
                agent_id=self._safe_uuid(agent_id),
                user_id=user_id,
                thread_id=key,
                memory_type="checkpoint",
                content={
                    "checkpoint": checkpoint,
                    "metadata": metadata,
                    "pending_writes": [],
                },
            )
            self.db.add(memory)

        self.db.commit()

        return {"configurable": {"thread_id": thread_id}}

    def put_writes(
        self,
        config: dict,
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """保存待写入的数据"""
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return

        key = f"checkpoint:{thread_id}:latest"
        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.thread_id == key,
                AgentMemory.memory_type == "checkpoint"
            )
            .limit(1)
        ).scalar_one_or_none()

        if memory:
            # 将 writes 合并到现有内容中
            existing_writes = memory.content.get("pending_writes", [])
            existing_writes.extend(writes)
            memory.content["pending_writes"] = existing_writes
            self.db.commit()

    def list(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[CheckpointMetadata] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """列出检查点"""
        thread_id = config["configurable"].get("thread_id") if config else None
        if not thread_id:
            return

        user_id, agent_id, session_id = self._parse_thread_id(thread_id)

        query = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.memory_type == "checkpoint"
        )

        if agent_id:
            query = query.where(AgentMemory.agent_id == agent_id)

        query = query.where(AgentMemory.thread_id.like(f"checkpoint:{thread_id}%"))
        query = query.order_by(AgentMemory.created_at.desc())

        if limit:
            query = query.limit(limit)

        results = self.db.execute(query).scalars().all()

        for memory in results:
            yield CheckpointTuple(
                checkpoint=memory.content.get("checkpoint", {}),
                metadata=memory.content.get("metadata", {}),
                pending_writes=memory.content.get("pending_writes", []),
                config=config,
            )

    def delete(self, config: dict) -> bool:
        """删除检查点"""
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return False

        key = self._get_checkpoint_key(config)

        self.db.execute(
            delete(AgentMemory).where(
                AgentMemory.thread_id == key,
                AgentMemory.memory_type == "checkpoint"
            )
        )
        self.db.commit()
        return True

    def get_channel_values(
        self,
        config: dict,
        channel_versions: dict[str, int],
        channel_names: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """获取通道值"""
        checkpoint_tuple = self.get_tuple(config)
        if checkpoint_tuple:
            return checkpoint_tuple.checkpoint.get("channel_values", {})
        return {}

    def get_channel_versions(
        self,
        config: dict,
    ) -> dict[str, int]:
        """获取通道版本"""
        checkpoint_tuple = self.get_tuple(config)
        if checkpoint_tuple:
            return checkpoint_tuple.checkpoint.get("channel_versions", {})
        return {}
