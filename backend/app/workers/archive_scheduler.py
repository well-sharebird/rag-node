"""
会话归档定时任务

使用 arq 实现定时归档：
- 每天凌晨 2 点执行归档任务
- 将 7 天前的会话归档到温/冷存储
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_factory
from app.services.conversation_archive_service import ConversationArchiveService

logger = logging.getLogger("app.workers.archive")


async def run_conversation_archive(ctx: dict) -> dict:
    """
    执行会话归档任务

    此函数由 arq worker 定时调用

    Args:
        ctx: arq context，包含 redis 等

    Returns:
        归档统计结果
    """
    logger.info(f"Starting conversation archive job at {datetime.utcnow()}")

    try:
        # 创建数据库 session
        async with async_session_factory() as db:
            service = ConversationArchiveService(db)
            result = await service.archive_old_conversations()

        logger.info(f"Archive job completed: {result}")
        return {
            "status": "success",
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Archive job failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def cleanup_expired_archives(ctx: dict) -> dict:
    """
    清理过期的冷归档数据

    删除超过配置天数的冷存储数据

    Args:
        ctx: arq context

    Returns:
        清理统计结果
    """
    logger.info(f"Starting expired archive cleanup at {datetime.utcnow()}")

    try:
        async with async_session_factory() as db:
            from app.models.conversation_archive import ConversationArchive, ConversationArchiveConfig
            from sqlalchemy import select, delete

            # 获取配置
            result = await db.execute(
                select(ConversationArchiveConfig)
                .where(ConversationArchiveConfig.is_enabled == True)
                .limit(1)
            )
            config = result.scalar_one_or_none()

            if not config:
                return {"status": "skipped", "reason": "No config found"}

            # 计算过期阈值
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(days=config.cold_tier_days)

            # 查询过期归档
            result = await db.execute(
                select(ConversationArchive)
                .where(ConversationArchive.archive_tier == "cold")
                .where(ConversationArchive.expires_at < datetime.utcnow())
                .limit(config.archive_batch_size)
            )
            expired = result.scalars().all()

            deleted_count = 0
            for archive in expired:
                try:
                    # 从 MinIO 删除
                    if archive.archive_path:
                        from app.core.minio import get_minio_client
                        minio = get_minio_client()
                        minio.remove_object(
                            bucket=config.minio_bucket,
                            object_name=archive.archive_path,
                        )

                    # 从数据库删除记录
                    await db.execute(
                        delete(ConversationArchive)
                        .where(ConversationArchive.id == archive.id)
                    )
                    deleted_count += 1

                except Exception as e:
                    logger.error(f"Failed to delete archive {archive.id}: {e}")

            await db.commit()

        logger.info(f"Cleanup completed: deleted {deleted_count} archives")
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Cleanup job failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


# arq worker 配置
async def startup(ctx):
    """arq worker 启动时的回调"""
    logger.info("Archive worker starting up...")


async def shutdown(ctx):
    """arq worker 关闭时的回调"""
    logger.info("Archive worker shutting down...")


# Worker 函数列表
archive_functions = [
    run_conversation_archive,
    cleanup_expired_archives,
]
