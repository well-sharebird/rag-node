"""
Sync Orchestrator - coordinates connector sync and document processing pipeline.

Connector -> Parse -> Chunk -> Embed -> Store Vectors
"""
from __future__ import annotations
import logging
import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import async_session_factory
from packages.rag.connectors.factory import create_connector
from packages.rag.connectors.base import Document as ConnectorDocument
from packages.rag.models.data_source import DataSource, SyncJob, SyncedItem
from packages.rag.services.parsing_service import parse_text
from packages.rag.services.chunking_service import chunk_text
from packages.rag.services.embedding_service import get_embedding_service
from packages.rag.services.vector_store_service import insert_chunks
from packages.rag.preprocessing.text_cleaner import get_text_cleaner
from packages.core.infra.milvus_client import get_milvus_client
from packages.rag.config import get_chunking_config
from packages.rag.models.knowledge_base import KnowledgeBase
from packages.rag.models.document import Document

logger = logging.getLogger("app.workers.sync_engine")


async def execute_sync_job(ctx: dict, job_id: int) -> dict:
    """
    Execute a data source sync job asynchronously (arq task).

    Steps:
    1. Load job and data source from DB
    2. Create appropriate connector
    3. Stream documents through parse -> chunk -> embed -> store pipeline
    4. Update job status and metrics
    """
    logger.info("Starting sync job | job_id=%d", job_id)

    async with async_session_factory() as db:
        try:
            # Load job
            result = await db.execute(select(SyncJob).where(SyncJob.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                logger.error("Sync job not found | job_id=%d", job_id)
                return {"status": "failed", "error": f"Job {job_id} not found"}

            # Load data source
            result = await db.execute(select(DataSource).where(DataSource.id == job.data_source_id))
            source = result.scalar_one_or_none()
            if not source:
                logger.error("Data source not found | source_id=%d", job.data_source_id)
                return {"status": "failed", "error": f"Source {job.data_source_id} not found"}

            # Load knowledge base
            result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == source.kb_id))
            kb = result.scalar_one_or_none()
            if not kb:
                logger.error("Knowledge base not found | kb_id=%s", source.kb_id)
                return {"status": "failed", "error": f"Knowledge base {source.kb_id} not found"}

            # Update job status
            job.status = "running"
            job.started_at = datetime.utcnow()
            source.status = "syncing"
            await db.commit()

            # Create connector
            connector = create_connector(source.source_type, source.config_json or {})
            if not connector:
                error_msg = f"No connector available for source type: {source.source_type}"
                logger.error(error_msg)
                await _fail_job(db, job, source, error_msg)
                return {"status": "failed", "error": error_msg}

            # Resolve embedding
            embed_params = await _resolve_embedding()
            embed_service = get_embedding_service(
                provider=embed_params["provider"],
                model_name=embed_params["model_name"],
                api_url=embed_params["api_url"],
                api_key=embed_params["api_key"],
                dim=embed_params["dim"],
            )
            chunk_cfg = get_chunking_config()
            milvus = get_milvus_client()

            # Stream documents through pipeline
            items_synced = 0
            items_failed = 0
            errors: list[str] = []

            async for connector_doc in connector.ingest():
                try:
                    # Parse
                    raw_text = await parse_text(connector_doc.content or "")

                    if not raw_text.strip():
                        logger.debug("Empty content for %s, skipping", connector_doc.external_id)
                        continue

                    # Stage 1.5: Preprocessing & Cleaning
                    cleaner = get_text_cleaner()
                    cleaning_result = cleaner.clean(raw_text)
                    text = cleaning_result.cleaned_text

                    # Skip low-quality content
                    if cleaning_result.quality_score < 0.3:
                        logger.debug("Low quality content (score=%.2f) for %s, skipping",
                                   cleaning_result.quality_score, connector_doc.external_id)
                        continue

                    # Skip duplicates
                    if cleaning_result.is_duplicate:
                        logger.debug("Duplicate content for %s, skipping", connector_doc.external_id)
                        continue

                    # Chunk
                    chunks = await chunk_text(
                        text,
                        strategy=chunk_cfg.get("strategy", "semantic"),
                        chunk_size=chunk_cfg.get("chunk_size", 512),
                        chunk_overlap=chunk_cfg.get("chunk_overlap", 50),
                        separators=chunk_cfg.get("separators"),
                    )
                    if not chunks:
                        continue

                    # Embed
                    chunk_texts = [c.text for c in chunks]
                    embeddings = await embed_service.embed_texts(chunk_texts)

                    # Store vectors
                    count = insert_chunks(
                        milvus, kb.collection_name,
                        f"ds_{source.id}_{connector_doc.external_id}",
                        kb.id,
                        connector_doc.title,
                        embeddings,
                        chunks,
                    )

                    # Track synced item
                    await _create_synced_item(db, job.id, source.id, connector_doc, len(chunks))

                    # Update KB counters
                    await db.execute(
                        update(KnowledgeBase)
                        .where(KnowledgeBase.id == kb.id)
                        .values(vector_count=KnowledgeBase.vector_count + count)
                    )

                    items_synced += 1
                    if items_synced % 10 == 0:
                        logger.info("Sync progress | job_id=%d items=%d", job_id, items_synced)

                except Exception as e:
                    items_failed += 1
                    error_msg = f"Error processing {connector_doc.external_id}: {e}"
                    errors.append(error_msg)
                    logger.warning("Sync item failed | %s", error_msg)

            # Complete
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.items_synced = items_synced
            job.items_failed = items_failed
            job.progress_percent = 100
            if errors:
                job.error_message = "; ".join(errors[:5])

            source.status = "active"
            source.last_sync_at = datetime.utcnow()
            source.last_sync_status = "completed"
            source.items_synced += items_synced
            source.items_failed += items_failed

            await db.commit()

            logger.info(
                "Sync completed | job_id=%d synced=%d failed=%d", job_id, items_synced, items_failed
            )
            return {"status": "completed", "items_synced": items_synced, "items_failed": items_failed}

        except Exception as e:
            await db.rollback()
            logger.exception("Sync job failed | job_id=%d | %s", job_id, e)
            await _fail_job(db, job, source, str(e))
            return {"status": "failed", "error": str(e)}


async def _fail_job(db: AsyncSession, job: SyncJob, source: DataSource, error: str):
    """Mark a job and source as failed"""
    job.status = "failed"
    job.completed_at = datetime.utcnow()
    job.error_message = error
    source.status = "error"
    source.last_sync_status = "failed"
    source.sync_message = error
    await db.commit()


async def _resolve_embedding() -> dict:
    """Resolve embedding model configuration"""
    from packages.rag.workers.document_pipeline import resolve_embedding_params
    return await resolve_embedding_params()


async def _create_synced_item(
    db: AsyncSession,
    job_id: int,
    source_id: int,
    doc: ConnectorDocument,
    chunk_count: int,
):
    """Track synced items for deduplication"""
    synced = SyncedItem(
        sync_job_id=job_id,
        data_source_id=source_id,
        external_id=doc.external_id,
        title=doc.title,
        url=doc.url,
        content_hash=doc.content_hash,
        item_count=chunk_count,
        metadata_json=doc.metadata,
    )
    db.add(synced)
