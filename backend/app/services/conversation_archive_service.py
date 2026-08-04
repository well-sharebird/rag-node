"""
会话归档服务
支持会话历史的分层存储（热/温/冷数据）

架构：
- 热数据 (0-7 天): agent_memories 表
- 温数据 (7-30 天): conversation_archives 表 (compressed_content)
- 冷数据 (30 天+): MinIO/S3 对象存储
"""
from __future__ import annotations
import gzip
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, distinct, text

from app.models.conversation_archive import ConversationArchive, ConversationArchiveConfig
from app.models.agent import AgentMemory
from app.core.minio_client import get_minio_client

logger = logging.getLogger("app.services.conversation_archive")

# 默认归档配置
DEFAULT_ARCHIVE_CONFIG = {
    "hot_tier_days": 7,
    "warm_tier_days": 30,
    "cold_tier_days": 365,
    "archive_batch_size": 100,
    "min_message_count": 5,
}


class ConversationArchiveService:
    """
    会话归档服务

    主要功能：
    1. 归档过期会话到温/冷存储
    2. 恢复归档的会话
    3. 查询分层会话历史
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._config: Optional[ConversationArchiveConfig] = None

    async def _get_config(self) -> ConversationArchiveConfig:
        """获取归档配置（带缓存）"""
        if self._config is None:
            result = await self.db.execute(
                select(ConversationArchiveConfig)
                .where(ConversationArchiveConfig.is_enabled == True)
                .limit(1)
            )
            self._config = result.scalar_one_or_none()
            if not self._config:
                # 创建默认配置
                self._config = ConversationArchiveConfig(
                    config_name="default",
                    **DEFAULT_ARCHIVE_CONFIG,
                )
                self.db.add(self._config)
                await self.db.commit()
                await self.db.refresh(self._config)
        return self._config

    async def archive_old_conversations(self) -> Dict[str, int]:
        """
        归档过期会话

        归档流程：
        1. 查询超过热数据期限的会话
        2. 按 thread_id 聚合消息
        3. 根据时间决定存入温层还是冷层
        4. 温层：压缩后存入 DB
        5. 冷层：上传到 MinIO，DB 只存元数据

        Returns:
            归档统计：{"warm_archived": N, "cold_archived": N, "errors": N}
        """
        config = await self._get_config()
        now = datetime.utcnow()

        # 计算归档时间阈值
        warm_threshold = now - timedelta(days=config.hot_tier_days)
        cold_threshold = now - timedelta(days=config.warm_tier_days)

        result = {"warm_archived": 0, "cold_archived": 0, "errors": 0}

        # 1. 查询需要归档的会话（按 thread_id 分组）
        threads_to_archive = await self._get_threads_to_archive(
            threshold=warm_threshold,
            batch_size=config.archive_batch_size,
            min_messages=config.min_message_count,
        )

        logger.info(f"Found {len(threads_to_archive)} threads to archive")

        for thread_id, agent_id, user_id, msg_count, min_created, max_created in threads_to_archive:
            try:
                # 2. 获取该 thread 的所有消息
                messages = await self._get_thread_messages(thread_id, min_created, max_created)

                if not messages:
                    continue

                # 3. 决定归档层级
                is_cold = max_created < cold_threshold
                archive_tier = "cold" if is_cold else "warm"

                # 4. 执行归档
                if is_cold:
                    await self._archive_to_cold(
                        user_id=user_id,
                        thread_id=thread_id,
                        agent_id=agent_id,
                        messages=messages,
                        date_range_start=min_created,
                        date_range_end=max_created,
                    )
                    result["cold_archived"] += 1
                else:
                    await self._archive_to_warm(
                        user_id=user_id,
                        thread_id=thread_id,
                        agent_id=agent_id,
                        messages=messages,
                        date_range_start=min_created,
                        date_range_end=max_created,
                    )
                    result["warm_archived"] += 1

            except Exception as e:
                logger.error(f"Failed to archive thread {thread_id}: {e}")
                result["errors"] += 1

        return result

    async def _get_threads_to_archive(
        self,
        threshold: datetime,
        batch_size: int,
        min_messages: int,
    ) -> List[Tuple]:
        """
        获取需要归档的会话列表

        Returns:
            List of (thread_id, agent_id, user_id, msg_count, min_created, max_created)
        """
        # 查询超过阈值的 thread，按 thread_id 聚合
        stmt = (
            select(
                AgentMemory.thread_id,
                AgentMemory.agent_id,
                AgentMemory.user_id,
                func.count(AgentMemory.id).label("msg_count"),
                func.min(AgentMemory.created_at).label("min_created"),
                func.max(AgentMemory.created_at).label("max_created"),
            )
            .where(AgentMemory.created_at < threshold)
            .where(AgentMemory.memory_type == "conversation")
            .group_by(AgentMemory.thread_id, AgentMemory.agent_id, AgentMemory.user_id)
            .having(func.count(AgentMemory.id) >= min_messages)
            .order_by(func.max(AgentMemory.created_at))
            .limit(batch_size)
        )

        result = await self.db.execute(stmt)
        return result.all()

    async def _get_thread_messages(
        self,
        thread_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict]:
        """获取指定 thread 的消息列表"""
        result = await self.db.execute(
            select(AgentMemory)
            .where(AgentMemory.thread_id == thread_id)
            .where(AgentMemory.created_at >= start_time)
            .where(AgentMemory.created_at <= end_time)
            .where(AgentMemory.memory_type == "conversation")
            .order_by(AgentMemory.created_at)
        )
        memories = result.scalars().all()

        messages = []
        for mem in memories:
            content = mem.content.get("messages", [])
            if isinstance(content, list):
                messages.extend(content)
            else:
                messages.append(content)

        return messages

    async def _archive_to_warm(
        self,
        user_id: int,
        thread_id: str,
        agent_id: str,
        messages: List[Dict],
        date_range_start: datetime,
        date_range_end: datetime,
    ):
        """归档到温存储（压缩后存入 DB）"""
        config = await self._get_config()

        # 1. 转换为 JSONL 格式
        jsonl_lines = []
        for msg in messages:
            jsonl_lines.append(json.dumps(msg, ensure_ascii=False))
        jsonl_content = "\n".join(jsonl_lines)

        # 2. 压缩
        if config.compression_enabled:
            compressed = gzip.compress(
                jsonl_content.encode("utf-8"),
                compresslevel=config.compression_level,
            )
        else:
            compressed = jsonl_content.encode("utf-8")

        # 3. 获取 agent 名称
        agent_name = await self._get_agent_name(agent_id)

        # 4. 创建归档记录
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=user_id,
            thread_id=thread_id,
            agent_id=agent_id,
            agent_name=agent_name,
            archive_tier="warm",
            message_count=len(messages),
            compressed_content=compressed,
            archive_size_bytes=len(compressed),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            summary=self._generate_summary(messages),
            keywords=self._extract_keywords(messages),
            last_message_preview=self._get_last_message_preview(messages),
            last_message_at=date_range_end,
        )

        self.db.add(archive)

        # 5. 删除原消息记录
        await self.db.execute(
            delete(AgentMemory)
            .where(AgentMemory.thread_id == thread_id)
            .where(AgentMemory.created_at >= date_range_start)
            .where(AgentMemory.created_at <= date_range_end)
            .where(AgentMemory.memory_type == "conversation")
        )

        await self.db.commit()
        logger.info(f"Archived thread {thread_id} to warm storage ({len(compressed)} bytes)")

    async def _archive_to_cold(
        self,
        user_id: int,
        thread_id: str,
        agent_id: str,
        messages: List[Dict],
        date_range_start: datetime,
        date_range_end: datetime,
    ):
        """归档到冷存储（MinIO/S3）"""
        config = await self._get_config()

        # 1. 转换为 JSONL 格式并压缩
        jsonl_lines = []
        for msg in messages:
            jsonl_lines.append(json.dumps(msg, ensure_ascii=False))
        jsonl_content = "\n".join(jsonl_lines)
        compressed = gzip.compress(
            jsonl_content.encode("utf-8"),
            compresslevel=config.compression_level,
        )

        # 2. 上传到 MinIO
        minio = get_minio_client()
        archive_path = f"{config.minio_prefix}/{user_id}/{thread_id}_{date_range_end.strftime('%Y%m%d')}.jsonl.gz"

        try:
            minio.put_object(
                bucket=config.minio_bucket,
                object_name=archive_path,
                data=compressed,
                length=len(compressed),
                content_type="application/gzip",
            )
        except Exception as e:
            logger.error(f"Failed to upload to MinIO: {e}")
            raise

        # 3. 获取 agent 名称
        agent_name = await self._get_agent_name(agent_id)

        # 4. 创建归档记录
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=user_id,
            thread_id=thread_id,
            agent_id=agent_id,
            agent_name=agent_name,
            archive_tier="cold",
            message_count=len(messages),
            archive_path=archive_path,
            archive_size_bytes=len(compressed),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            summary=self._generate_summary(messages),
            keywords=self._extract_keywords(messages),
            last_message_preview=self._get_last_message_preview(messages),
            last_message_at=date_range_end,
            expires_at=date_range_end + timedelta(days=config.cold_tier_days),
        )

        self.db.add(archive)

        # 5. 删除原消息记录
        await self.db.execute(
            delete(AgentMemory)
            .where(AgentMemory.thread_id == thread_id)
            .where(AgentMemory.created_at >= date_range_start)
            .where(AgentMemory.created_at <= date_range_end)
            .where(AgentMemory.memory_type == "conversation")
        )

        await self.db.commit()
        logger.info(f"Archived thread {thread_id} to cold storage ({archive_path})")

    async def restore_archive(self, archive_id: str) -> bool:
        """
        恢复归档的会话到热存储

        Args:
            archive_id: 归档记录 ID

        Returns:
            True if restored successfully
        """
        result = await self.db.execute(
            select(ConversationArchive)
            .where(ConversationArchive.id == archive_id)
        )
        archive = result.scalar_one_or_none()

        if not archive:
            raise ValueError(f"Archive not found: {archive_id}")

        # 从温存储恢复
        if archive.archive_tier == "warm":
            if not archive.compressed_content:
                raise ValueError("Warm archive has no content")

            # 解压
            if archive.compressed_content:
                decompressed = gzip.decompress(archive.compressed_content).decode("utf-8")
            else:
                decompressed = archive.compressed_content.decode("utf-8")

            # 解析 JSONL
            messages = []
            for line in decompressed.split("\n"):
                if line.strip():
                    messages.append(json.loads(line))

            # 写回 agent_memories
            from app.models.agent import AgentMemory
            memory = AgentMemory(
                id=str(uuid4()),
                agent_id=archive.agent_id,
                user_id=archive.user_id,
                thread_id=archive.thread_id,
                memory_type="conversation",
                content={"messages": messages},
            )
            self.db.add(memory)

        # 从冷存储恢复
        elif archive.archive_tier == "cold":
            if not archive.archive_path:
                raise ValueError("Cold archive has no path")

            # 从 MinIO 下载
            config = await self._get_config()
            minio = get_minio_client()

            try:
                response = minio.get_object(
                    bucket=config.minio_bucket,
                    object_name=archive.archive_path,
                )
                compressed = response.read()
                decompressed = gzip.decompress(compressed).decode("utf-8")
            except Exception as e:
                logger.error(f"Failed to download from MinIO: {e}")
                raise

            # 解析 JSONL
            messages = []
            for line in decompressed.split("\n"):
                if line.strip():
                    messages.append(json.loads(line))

            # 写回 agent_memories
            from app.models.agent import AgentMemory
            memory = AgentMemory(
                id=str(uuid4()),
                agent_id=archive.agent_id,
                user_id=archive.user_id,
                thread_id=archive.thread_id,
                memory_type="conversation",
                content={"messages": messages},
            )
            self.db.add(memory)

        # 标记为已恢复
        archive.is_restored = True
        await self.db.commit()

        logger.info(f"Restored archive {archive_id} for thread {archive.thread_id}")
        return True

    async def get_conversation_history(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        agent_id: Optional[str] = None,
        time_range: Optional[str] = None,  # "7d" | "30d" | "month" | "all"
        month: Optional[str] = None,  # "2026-01" 格式
    ) -> Tuple[List[Dict], int]:
        """
        获取会话历史（跨热/温/冷三层查询）

        Args:
            user_id: 用户 ID
            limit: 每页数量
            offset: 偏移量
            agent_id: 智能体 ID 过滤
            time_range: 时间范围 ("7d" | "30d" | "month" | "all")
            month: 月份 ("2026-01")，当 time_range="month" 时使用

        Returns:
            (列表，总数)
        """
        config = await self._get_config()
        now = datetime.utcnow()

        # 根据 time_range 计算时间阈值
        if time_range == "7d":
            threshold = now - timedelta(days=7)
        elif time_range == "30d":
            threshold = now - timedelta(days=30)
        elif time_range == "month" and month:
            # 解析月份，查询该月的数据
            year, month_num = map(int, month.split("-"))
            month_start = datetime(year, month_num, 1)
            if month_num == 12:
                month_end = datetime(year + 1, 1, 1)
            else:
                month_end = datetime(year, month_num + 1, 1)
            threshold = month_start
        else:  # "all" or default
            threshold = datetime(2000, 1, 1)  # 很早的时间，获取全部

        # 1. 先查热数据
        hot_threshold = now - timedelta(days=config.hot_tier_days)

        # 热数据：从 agent_memories 聚合
        hot_stmt = (
            select(
                AgentMemory.thread_id,
                AgentMemory.agent_id,
                func.count(AgentMemory.id).label("msg_count"),
                func.max(AgentMemory.created_at).label("last_message_at"),
            )
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.created_at > hot_threshold)
            .where(AgentMemory.created_at > threshold)
            .where(AgentMemory.memory_type == "conversation")
        )

        if agent_id:
            hot_stmt = hot_stmt.where(AgentMemory.agent_id == agent_id)

        hot_stmt = (
            hot_stmt
            .group_by(AgentMemory.thread_id, AgentMemory.agent_id)
            .order_by(func.max(AgentMemory.created_at).desc())
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_threads = hot_result.all()

        # 2. 从归档数据补充
        archive_stmt = (
            select(
                ConversationArchive.thread_id,
                ConversationArchive.agent_id,
                ConversationArchive.message_count,
                ConversationArchive.last_message_at,
                ConversationArchive.agent_name,
                ConversationArchive.summary,
                ConversationArchive.archive_tier,
            )
            .where(ConversationArchive.user_id == user_id)
            .where(ConversationArchive.is_restored == False)
        )

        # 应用时间范围过滤
        if time_range == "7d":
            archive_stmt = archive_stmt.where(ConversationArchive.last_message_at > threshold)
        elif time_range == "30d":
            archive_stmt = archive_stmt.where(ConversationArchive.last_message_at > threshold)
        elif time_range == "month" and month:
            archive_stmt = archive_stmt.where(
                ConversationArchive.last_message_at >= month_start
            ).where(
                ConversationArchive.last_message_at < month_end
            )

        if agent_id:
            archive_stmt = archive_stmt.where(ConversationArchive.agent_id == agent_id)

        archive_stmt = (
            archive_stmt
            .order_by(ConversationArchive.last_message_at.desc())
        )

        archive_result = await self.db.execute(archive_stmt)
        archive_threads = archive_result.all()

        # 合并结果（已经按时间排序）
        all_threads = [
            {
                "thread_id": t.thread_id,
                "agent_id": str(t.agent_id) if t.agent_id else None,
                "agent_name": None,
                "summary": None,
                "message_count": t.msg_count,
                "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
                "source": "hot",
                "archive_tier": None,
            }
            for t in hot_threads
        ] + [
            {
                "thread_id": t.thread_id,
                "agent_id": str(t.agent_id) if t.agent_id else None,
                "message_count": t.message_count,
                "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
                "agent_name": t.agent_name,
                "summary": t.summary,
                "source": "archive",
                "archive_tier": t.archive_tier,
            }
            for t in archive_threads
        ]

        # 应用分页
        paginated_threads = all_threads[offset:offset + limit]

        # 3. 获取总数（当前时间范围内的总数，用于前端分页）
        total = len(all_threads)

        return paginated_threads, total

    async def get_conversation_history_stats(
        self,
        user_id: int,
        agent_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        获取会话历史统计（按时间段分组）

        Returns:
            各时间段的会话数量：
            {
                "last_7d": 10,
                "last_30d": 25,
                "months": {"2026-01": 15, "2025-12": 20, ...}
            }
        """
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        result = {"last_7d": 0, "last_30d": 0, "months": {}}

        # 统计热数据（最近 7 天）
        hot_7d_stmt = (
            select(func.count(distinct(AgentMemory.thread_id)))
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.created_at > seven_days_ago)
            .where(AgentMemory.memory_type == "conversation")
        )
        if agent_id:
            hot_7d_stmt = hot_7d_stmt.where(AgentMemory.agent_id == agent_id)
        hot_7d_result = await self.db.execute(hot_7d_stmt)
        result["last_7d"] = hot_7d_result.scalar() or 0

        # 统计热数据（最近 30 天）
        hot_30d_stmt = (
            select(func.count(distinct(AgentMemory.thread_id)))
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.created_at > thirty_days_ago)
            .where(AgentMemory.memory_type == "conversation")
        )
        if agent_id:
            hot_30d_stmt = hot_30d_stmt.where(AgentMemory.agent_id == agent_id)
        hot_30d_result = await self.db.execute(hot_30d_stmt)
        result["last_30d"] = hot_30d_result.scalar() or 0

        # 统计 30 天内的归档数据并加入 last_30d
        archive_30d_query = text("""
            SELECT COUNT(DISTINCT thread_id) as count
            FROM conversation_archives
            WHERE user_id = :user_id
              AND is_restored = false
              AND last_message_at > :thirty_days_ago
        """)
        if agent_id:
            archive_30d_query = text("""
                SELECT COUNT(DISTINCT thread_id) as count
                FROM conversation_archives
                WHERE user_id = :user_id
                  AND is_restored = false
                  AND agent_id = :agent_id
                  AND last_message_at > :thirty_days_ago
            """)

        archive_30d_result = await self.db.execute(
            archive_30d_query,
            {"user_id": user_id, "thirty_days_ago": thirty_days_ago, "agent_id": agent_id} if agent_id else {"user_id": user_id, "thirty_days_ago": thirty_days_ago}
        )
        archive_30d_count = archive_30d_result.scalar() or 0
        result["last_30d"] += archive_30d_count

        # 统计归档数据（按月份分组）
        archive_query = text("""
            SELECT TO_CHAR(last_message_at, 'YYYY-MM') as month, COUNT(thread_id) as count
            FROM conversation_archives
            WHERE user_id = :user_id AND is_restored = false
            GROUP BY TO_CHAR(last_message_at, 'YYYY-MM')
            ORDER BY month DESC
        """)

        if agent_id:
            archive_query = text("""
                SELECT TO_CHAR(last_message_at, 'YYYY-MM') as month, COUNT(thread_id) as count
                FROM conversation_archives
                WHERE user_id = :user_id AND is_restored = false AND agent_id = :agent_id
                GROUP BY TO_CHAR(last_message_at, 'YYYY-MM')
                ORDER BY month DESC
            """)

        archive_result = await self.db.execute(
            archive_query,
            {"user_id": user_id, "agent_id": agent_id} if agent_id else {"user_id": user_id}
        )

        for row in archive_result.all():
            month_key = row[0]
            count = row[1]
            result["months"][month_key] = result["months"].get(month_key, 0) + count

        return result

    async def get_archive_content(self, archive_id: str) -> List[Dict]:
        """获取归档会话的完整内容"""
        result = await self.db.execute(
            select(ConversationArchive)
            .where(ConversationArchive.id == archive_id)
        )
        archive = result.scalar_one_or_none()

        if not archive:
            raise ValueError(f"Archive not found: {archive_id}")

        if archive.archive_tier == "warm":
            # 从 compressed_content 解压
            if archive.compressed_content:
                decompressed = gzip.decompress(archive.compressed_content).decode("utf-8")
            else:
                decompressed = archive.compressed_content.decode("utf-8")

            messages = []
            for line in decompressed.split("\n"):
                if line.strip():
                    messages.append(json.loads(line))
            return messages

        elif archive.archive_tier == "cold":
            # 从 MinIO 下载
            if not archive.archive_path:
                raise ValueError("Cold archive has no path")

            config = await self._get_config()
            minio = get_minio_client()

            response = minio.get_object(
                bucket=config.minio_bucket,
                object_name=archive.archive_path,
            )
            compressed = response.read()
            decompressed = gzip.decompress(compressed).decode("utf-8")

            messages = []
            for line in decompressed.split("\n"):
                if line.strip():
                    messages.append(json.loads(line))
            return messages

        return []

    def _generate_summary(self, messages: List[Dict]) -> str:
        """生成会话摘要（简单版，实际可用 LLM）"""
        if not messages:
            return ""

        # 简单提取前几条消息的关键信息
        user_messages = [m for m in messages if m.get("role") == "user"]
        if user_messages:
            first_msg = user_messages[0].get("content", "")[:100]
            return f"用户询问：{first_msg}..." if first_msg else ""
        return ""

    def _extract_keywords(self, messages: List[Dict]) -> List[str]:
        """提取关键词（简单版）"""
        # 实际可用 LLM 或 TF-IDF 提取
        return []

    def _get_last_message_preview(self, messages: List[Dict]) -> str:
        """获取最后一条消息的预览"""
        if not messages:
            return ""

        last_msg = messages[-1].get("content", "")
        return last_msg[:100] if last_msg else ""

    async def _get_agent_name(self, agent_id: str) -> Optional[str]:
        """获取 Agent 名称"""
        if not agent_id:
            return None

        from app.models.agent import AgentConfig
        result = await self.db.execute(
            select(AgentConfig.name)
            .where(AgentConfig.id == agent_id)
        )
        row = result.scalar_one_or_none()
        return row
