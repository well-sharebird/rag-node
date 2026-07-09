from __future__ import annotations
from arq.worker import create_worker

from app.config import settings
from app.workers.document_pipeline import process_document


async def startup(ctx):
    pass


async def shutdown(ctx):
    from app.core.milvus_client import close_milvus_client
    from app.core.redis_client import close_redis
    close_milvus_client()
    await close_redis()


async def main():
    worker = create_worker(
        redis_settings=settings.redis_url,
        functions=[process_document],
        queue_name="arq:queue",
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
