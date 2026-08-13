"""异步检查点持久化 - LangGraph 层（Checkpoint 归属 LangGraph 铁律）

LangGraph 新版本要求 checkpoint saver 提供异步 API（aget_tuple/aput/aput_writes）。
现有 DatabaseCheckpointSaver 仅实现同步方法，此处用一个包装器把同步实现适配为异步，
复用底层 PostgreSQL 持久化，并通过线程池 + 锁保证线程安全。
"""
import asyncio
import logging
import threading
from typing import Any, AsyncIterator, Dict, Optional, Sequence

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

logger = logging.getLogger(__name__)


def create_async_checkpointer() -> Optional[BaseCheckpointSaver]:
    """创建异步数据库检查点持久化器（数据库不可用时返回 None）。

    DatabaseCheckpointSaver 使用同步 SQLAlchemy Session，因此需要独立的同步
    PostgreSQL 引擎（asyncpg 的 sync_engine 在无 greenlet 上下文的线程中不可用）。
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from packages.agent.services.agent_checkpoint_service import DatabaseCheckpointSaver

        from packages.core.config import settings
        sync_url = settings.database_url.replace("+asyncpg", "")
        # SQLAlchemy 2.x 同步驱动优先 psycopg2；不支持时回退原 URL
        sync_engine = create_engine(sync_url, pool_pre_ping=True)

        sync_saver = DatabaseCheckpointSaver(sessionmaker(bind=sync_engine)())
        logger.info("[Checkpointer] 数据库检查点已启用 | %s", sync_url.split("@")[-1])
        return AsyncDatabaseCheckpointSaver(sync_saver)
    except Exception as e:
        logger.warning("[Checkpointer] 数据库检查点不可用，禁用持久化: %s", e)
        return None


class AsyncDatabaseCheckpointSaver(BaseCheckpointSaver):
    """把同步 DatabaseCheckpointSaver 适配为 LangGraph 异步接口。"""

    def __init__(self, sync_saver: BaseCheckpointSaver):
        super().__init__()
        self._sync = sync_saver
        self._lock = threading.Lock()

    @staticmethod
    def _thread_id(config: dict) -> str:
        return (config.get("configurable") or {}).get("thread_id", "default")

    # ---------- 恢复 ----------
    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        return await asyncio.to_thread(self._get_tuple_locked, config)

    def _get_tuple_locked(self, config: dict) -> Optional[CheckpointTuple]:
        with self._lock:
            return self._sync.get_tuple(config)

    # ---------- 保存 ----------
    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> dict:
        return await asyncio.to_thread(
            self._put_locked, config, checkpoint, metadata
        )

    def _put_locked(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> dict:
        with self._lock:
            return self._sync.put(
                config, checkpoint, metadata, new_values={}, saved=None
            )

    async def aput_writes(
        self,
        config: dict,
        writes: Sequence[tuple],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self._put_writes_locked, config, writes, task_id)

    def _put_writes_locked(
        self,
        config: dict,
        writes: Sequence[tuple],
        task_id: str,
    ) -> None:
        with self._lock:
            self._sync.put_writes(config, writes, task_id)

    # ---------- 列举 ----------
    async def alist(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        items = await asyncio.to_thread(self._list_locked, config, limit)
        for item in items:
            yield item

    def _list_locked(
        self,
        config: Optional[dict],
        limit: Optional[int],
    ):
        with self._lock:
            return list(self._sync.list(config, limit=limit))

    # ---------- 删除 ----------
    async def adelete_thread(self, thread_id: str) -> None:
        config = {"configurable": {"thread_id": thread_id}}
        await asyncio.to_thread(self._delete_locked, config)

    def _delete_locked(self, config: dict) -> None:
        with self._lock:
            self._sync.delete(config)

    # ---------- 取状态快照 ----------
    async def aget(self, config: dict) -> Optional[Checkpoint]:
        t = await self.aget_tuple(config)
        return t.checkpoint if t else None
