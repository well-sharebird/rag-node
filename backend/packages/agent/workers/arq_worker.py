from __future__ import annotations
from arq.worker import create_worker
from arq.cron import cron

from packages.core.config import settings
from packages.rag.workers.document_pipeline import process_document
from packages.agent.workers.archive_scheduler import (
    run_conversation_archive,
    cleanup_expired_archives,
    startup as archive_startup,
    shutdown as archive_shutdown,
)


async def startup(ctx):
    await archive_startup(ctx)


async def shutdown(ctx):
    from packages.core.infra.milvus_client import close_milvus_client
    from packages.core.infra.redis_client import close_redis
    close_milvus_client()
    await close_redis()
    await archive_shutdown(ctx)


# 定时任务配置
cron_jobs = [
    # 每天凌晨 2 点执行归档
    cron(run_conversation_archive, hour=2, minute=0),
    # 每周日凌晨 3 点清理过期归档
    cron(cleanup_expired_archives, hour=3, minute=0, weekday=0),
]


async def main():
    worker = create_worker(
        redis_settings=settings.redis_url,
        functions=[process_document, run_conversation_archive, cleanup_expired_archives],
        queue_name="arq:queue",
        cron_jobs=cron_jobs,
        max_jobs=10,
        job_timeout=600,
        poll_delay=0.5,
        on_startup=startup,
        on_shutdown=shutdown,
    )
    await worker.async_run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
