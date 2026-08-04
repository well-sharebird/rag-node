"""
Agent 记忆服务
管理对话历史、向量记忆等
"""
from __future__ import annotations
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from packages.agent.models.agent import AgentMemory, AgentConfig


class AgentMemoryService:
    """
    Agent 记忆服务

    支持三种记忆类型：
    1. conversation: 对话历史（JSON 存储）
    2. vector: 向量记忆（Milvus 存储向量，PostgreSQL 存引用）
    3. summary: 对话摘要
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_conversation(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str,
        messages: List[dict],
        ttl_hours: int = 24
    ) -> str:
        """添加对话记忆"""
        memory_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        memory = AgentMemory(
            id=memory_id,
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            memory_type="conversation",
            content={"messages": messages},
            expires_at=expires_at,
        )
        self.db.add(memory)
        await self.db.commit()
        return memory_id

    async def get_conversation(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str,
        limit: int = 50
    ) -> List[dict]:
        """获取对话历史"""
        result = await self.db.execute(
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == user_id,
                AgentMemory.thread_id == thread_id,
                AgentMemory.memory_type == "conversation",
                AgentMemory.expires_at > datetime.utcnow()
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(limit)
        )
        memories = result.scalars().all()

        all_messages = []
        for memory in reversed(memories):
            messages = memory.content.get("messages", [])
            all_messages.extend(messages)

        return all_messages[-limit:]

    async def clear_conversation(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str
    ) -> int:
        """清除对话历史"""
        result = await self.db.execute(
            delete(AgentMemory).where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == user_id,
                AgentMemory.thread_id == thread_id,
                AgentMemory.memory_type == "conversation"
            )
        )
        await self.db.commit()
        return result.rowcount

    async def add_vector_memory(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str,
        text: str,
        milvus_collection: str,
        milvus_ids: List[str]
    ) -> str:
        """添加向量记忆"""
        memory_id = str(uuid4())

        memory = AgentMemory(
            id=memory_id,
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            memory_type="vector",
            content={"text": text},
            milvus_collection=milvus_collection,
            milvus_ids=milvus_ids,
        )
        self.db.add(memory)
        await self.db.commit()
        return memory_id

    async def get_vector_memory_refs(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str
    ) -> List[Tuple[str, List[str]]]:
        """获取向量记忆引用（用于从 Milvus 查询）"""
        result = await self.db.execute(
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == user_id,
                AgentMemory.thread_id == thread_id,
                AgentMemory.memory_type == "vector"
            )
        )
        memories = result.scalars().all()

        return [(m.milvus_collection, m.milvus_ids) for m in memories if m.milvus_ids]

    async def add_summary(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str,
        summary: str,
        keywords: List[str]
    ) -> str:
        """添加对话摘要"""
        memory_id = str(uuid4())

        memory = AgentMemory(
            id=memory_id,
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            memory_type="summary",
            content={"summary": summary, "keywords": keywords},
        )
        self.db.add(memory)
        await self.db.commit()
        return memory_id

    async def get_summary(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str
    ) -> Optional[dict]:
        """获取对话摘要"""
        result = await self.db.execute(
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == user_id,
                AgentMemory.thread_id == thread_id,
                AgentMemory.memory_type == "summary"
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(1)
        )
        memory = result.scalar_one_or_none()

        return memory.content if memory else None

    async def cleanup_expired(self) -> int:
        """清理过期记忆"""
        result = await self.db.execute(
            delete(AgentMemory).where(
                AgentMemory.expires_at < datetime.utcnow()
            )
        )
        await self.db.commit()
        return result.rowcount
