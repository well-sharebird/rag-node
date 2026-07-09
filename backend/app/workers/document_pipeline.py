"""Document processing pipeline: parse -> chunk -> embed -> store vectors.

Uses model_configs table for embedding model configuration.
Falls back to legacy system_settings if no model is configured in model management.
"""
from __future__ import annotations
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.milvus_client import get_milvus_client
from app.core.minio_client import get_minio_client
from app.config import settings as app_settings
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.parsing_service import parse_document
from app.services.chunking_service import chunk_text
from app.services.embedding_service import get_embedding_service
from app.services.vector_store_service import insert_chunks

logger = logging.getLogger("app.workers.pipeline")


async def resolve_embedding_params() -> dict:
    """Resolve embedding parameters from model_configs.

    Priority:
    1. Default embedding model from model_configs (is_default=True, is_enabled=True)
    2. Any enabled embedding model from model_configs
    3. Error if no enabled embedding model configured
    """
    from app.core.database import async_session_factory
    from app.services.model_config_service import resolve_embedding_config
    from app.models.model_config import ModelConfig
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            # Try default model first
            model = await resolve_embedding_config(session)
            if model:
                logger.info("Using default embedding model: %s", model.name)
                return _model_to_params(model)

            # Try any enabled embedding model
            result = await session.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == "embedding")
                .where(ModelConfig.is_enabled == True)
                .order_by(ModelConfig.updated_at.desc())
                .limit(1)
            )
            model = result.scalar_one_or_none()
            if model:
                logger.info("Using available embedding model: %s (not default)", model.name)
                # Auto-set as default for future use
                await session.execute(
                    update(ModelConfig)
                    .where(ModelConfig.id == model.id)
                    .values(is_default=True)
                )
                await session.commit()
                return _model_to_params(model)

    except Exception as e:
        logger.warning("Failed to resolve embedding from model_configs: %s", e)

    raise ValueError(
        "No embedding model configured. Please go to Model Management and configure an embedding model, "
        "then set it as default."
    )


def _model_to_params(model) -> dict:
    """Convert ModelConfig to embedding service parameters."""
    return {
        "provider": model.adapter_type,
        "model_name": model.model_id,
        "api_url": model.api_url or "",
        "api_key": model.api_key or "",
        "dim": model.embedding_dim or 1024,
    }


async def process_document(ctx: dict, doc_id: str):
    """arq job: parse -> chunk -> embed -> store vectors"""
    logger.info("Processing document | doc_id=%s", doc_id)

    async with async_session_factory() as db:
        try:
            await db.execute(update(Document).where(Document.id == doc_id).values(status="processing"))
            await db.commit()

            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one()
            if doc is None:
                logger.error("Document not found | doc_id=%s", doc_id)
                return

            kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
            kb = kb_result.scalar_one()

            # Get document content from MinIO
            minio = get_minio_client()
            obj = minio.get_object(app_settings.minio_bucket, doc.minio_key)
            content = obj.read()
            obj.close()
            obj.release_conn()
            text = await parse_document(content, doc.format)

            if not text.strip():
                raise ValueError("Document produced no text content")

            # Chunk — read strategy from system settings
            from app.core.rag_config import get_chunking_config
            chunk_cfg = get_chunking_config()
            chunks = chunk_text(
                text,
                strategy=chunk_cfg.get("strategy", "semantic"),
                chunk_size=chunk_cfg.get("chunk_size", 512),
                chunk_overlap=chunk_cfg.get("chunk_overlap", 50),
                separators=chunk_cfg.get("separators"),
            )
            if not chunks:
                raise ValueError("Document could not be chunked")
            logger.info("Document chunked | doc_id=%s chunks=%d", doc_id, len(chunks))

            # Embed — resolve from model_configs or fallback to legacy
            embed_params = await resolve_embedding_params()
            logger.info("Embedding params | provider=%s model=%s", embed_params["provider"], embed_params["model_name"])

            embed_service = get_embedding_service(
                provider=embed_params["provider"],
                model_name=embed_params["model_name"],
                api_url=embed_params["api_url"],
                api_key=embed_params["api_key"],
                dim=embed_params["dim"],
            )
            chunk_texts = [c.text for c in chunks]
            embeddings = await embed_service.embed_texts(chunk_texts)
            logger.info("Document embedded | doc_id=%s vectors=%d dim=%d", doc_id, len(embeddings), len(embeddings[0]) if embeddings else 0)

            # Insert into vector store
            milvus = get_milvus_client()
            count = insert_chunks(
                milvus, kb.collection_name, doc.id, kb.id,
                doc.original_name, embeddings, chunks,
            )
            logger.info("Vectors inserted | doc_id=%s collection=%s count=%d", doc_id, kb.collection_name, count)

            # Update document + KB counters
            await db.execute(
                update(Document).where(Document.id == doc_id).values(status="completed", chunk_count=count)
            )
            await db.execute(
                update(KnowledgeBase).where(KnowledgeBase.id == kb.id).values(
                    vector_count=KnowledgeBase.vector_count + count
                )
            )
            await db.commit()

            logger.info("Document processing completed | doc_id=%s chunks=%d", doc_id, count)
            return {"status": "completed", "chunks": count, "embedding_model": embed_params["model_name"]}

        except Exception as e:
            await db.rollback()
            error_msg = f"{type(e).__name__}: {e}"
            logger.exception("Document processing failed | doc_id=%s | %s", doc_id, error_msg)
            await db.execute(
                update(Document).where(Document.id == doc_id).values(status="failed", error_message=error_msg)
            )
            await db.commit()
            return {"status": "failed", "error": error_msg}
