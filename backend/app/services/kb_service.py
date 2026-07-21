from __future__ import annotations
import logging
import uuid
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.schemas.knowledge_base import KBCreateRequest, KBUpdateRequest
from app.utils.exceptions import NotFoundException

logger = logging.getLogger("app.services.kb")


def _make_collection_name() -> str:
    return f"kb_{uuid.uuid4().hex[:12]}"


def _create_milvus_collection(milvus, collection_name: str, dim: int = 1024):
    if milvus.has_collection(collection_name):
        return

    # Use IndexParams for pymilvus 3.0+ compatibility
    from pymilvus.milvus_client.index import IndexParams
    index_params = IndexParams()
    index_params.add_index(field_name="vector", index_type="FLAT", metric_type="IP")

    milvus.create_collection(
        collection_name=collection_name,
        dimension=dim,
        metric_type="IP",
        auto_id=True,
        index_params=index_params,
    )
    logger.info("Milvus collection created: %s (dim=%d)", collection_name, dim)


def _drop_milvus_collection(milvus, collection_name: str):
    if milvus.has_collection(collection_name):
        milvus.drop_collection(collection_name)
        logger.info("Milvus collection dropped: %s", collection_name)


async def list_knowledge_bases(db: AsyncSession, search: str = "") -> list[KnowledgeBase]:
    stmt = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
    if search:
        stmt = stmt.where(
            (KnowledgeBase.name.ilike(f"%{search}%"))
            | (KnowledgeBase.description.ilike(f"%{search}%"))
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_knowledge_base(db: AsyncSession, kb_id: str) -> KnowledgeBase:
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("Knowledge base not found")
    return kb


async def create_knowledge_base(db: AsyncSession, milvus, data: KBCreateRequest) -> KnowledgeBase:
    # Get embedding dimension from configured model
    from app.services.model_config_service import get_default_model, ModelType

    embedding_model = await get_default_model(db, ModelType.EMBEDDING.value)
    dim = embedding_model.embedding_dim if embedding_model else 1024

    collection_name = _make_collection_name()
    _create_milvus_collection(milvus, collection_name, dim)

    kb = KnowledgeBase(
        name=data.name, description=data.description,
        collection_name=collection_name, permissions=data.permissions,
    )
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    logger.info("Knowledge base created | id=%s name=%s collection=%s dim=%d", kb.id, kb.name, collection_name, dim)
    return kb


async def update_knowledge_base(db: AsyncSession, kb_id: str, data: KBUpdateRequest) -> KnowledgeBase:
    kb = await get_knowledge_base(db, kb_id)
    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(update(KnowledgeBase).where(KnowledgeBase.id == kb_id).values(**update_data))
        await db.flush()
        await db.refresh(kb)
        logger.info("Knowledge base updated | id=%s fields=%s", kb_id, list(update_data.keys()))
    return kb


async def delete_knowledge_base(db: AsyncSession, milvus, kb_id: str) -> None:
    kb = await get_knowledge_base(db, kb_id)
    _drop_milvus_collection(milvus, kb.collection_name)
    await db.delete(kb)
    await db.flush()
    logger.info("Knowledge base deleted | id=%s name=%s", kb_id, kb.name)
