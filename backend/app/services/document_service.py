from __future__ import annotations
import io
import json
import logging
import time
import uuid
from datetime import datetime
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document import DocumentResponse
from app.utils.exceptions import NotFoundException, ValidationException

logger = logging.getLogger("app.services.document")

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx", "txt", "md", "html", "htm"}
MAX_FILE_SIZE = 50 * 1024 * 1024


async def list_documents(
    db: AsyncSession,
    kb_id: str | None = None,
    search: str = "",
    category: str | None = None,
    tag: str | None = None,
) -> list[DocumentResponse]:
    stmt = select(
        Document,
        KnowledgeBase.name.label("kb_name"),
    ).join(
        KnowledgeBase, Document.kb_id == KnowledgeBase.id, isouter=True
    ).order_by(Document.uploaded_at.desc())

    if kb_id:
        stmt = stmt.where(Document.kb_id == kb_id)
    if search:
        stmt = stmt.where(Document.original_name.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Document.category == category)
    if tag:
        stmt = stmt.where(Document.tags.ilike(f"%{tag}%"))

    result = await db.execute(stmt)
    rows = result.all()

    docs = []
    for row in rows:
        docs.append(DocumentResponse(
            id=row.Document.id,
            kb_id=row.Document.kb_id,
            name=row.Document.original_name,
            format=row.Document.format,
            file_size=row.Document.file_size,
            status=row.Document.status,
            error_message=row.Document.error_message,
            uploaded_at=row.Document.uploaded_at,
            processed_at=row.Document.processed_at,
            chunk_count=row.Document.chunk_count,
            category=row.Document.category or "",
            tags=row.Document.tags_list,
            kb_name=row.kb_name,
        ))
    return docs


async def get_categories(db: AsyncSession, kb_id: str | None = None) -> list[str]:
    """Get distinct categories for a knowledge base."""
    stmt = select(Document.category).where(Document.category != "").distinct()
    if kb_id:
        stmt = stmt.where(Document.kb_id == kb_id)
    result = await db.execute(stmt)
    return sorted([r[0] for r in result.all() if r[0]])


async def get_all_tags(db: AsyncSession, kb_id: str | None = None) -> list[str]:
    """Get all unique tags across documents."""
    stmt = select(Document.tags).where(Document.tags.isnot(None)).where(Document.tags != "")
    if kb_id:
        stmt = stmt.where(Document.kb_id == kb_id)
    result = await db.execute(stmt)
    all_tags = set()
    for row in result:
        try:
            tags = json.loads(row[0])
            all_tags.update(tags)
        except:
            pass
    return sorted(all_tags)


async def update_document_metadata(
    db: AsyncSession, doc_id: str, data: dict
) -> Document | None:
    """Update document metadata (category, tags)."""
    doc = await get_document(db, doc_id)
    if not doc:
        return None

    if "category" in data:
        doc.category = data["category"]
    if "tags" in data and data["tags"] is not None:
        doc.tags_list = data["tags"]

    await db.flush()
    await db.refresh(doc)
    return doc


async def get_document(db: AsyncSession, doc_id: str) -> Document:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundException("Document not found")
    return doc


def _put_object_with_retry(minio, bucket: str, key: str, content: bytes, file_size: int, max_retries: int = 3):
    """Upload to MinIO with exponential backoff retry for rate limits."""
    last_error = None
    for attempt in range(max_retries):
        try:
            minio.put_object(bucket, key, io.BytesIO(content), file_size, content_type="application/octet-stream")
            return
        except Exception as e:
            last_error = e
            error_str = str(e)
            if "SlowDown" in error_str or "timeout" in error_str.lower():
                delay = 2 ** attempt  # 1s, 2s, 4s
                logger.warning("MinIO rate limited (attempt %d/%d), retrying in %ds: %s", attempt + 1, max_retries, delay, e)
                time.sleep(delay)
                continue
            raise
    raise last_error


def validate_file(filename: str, file_size: int):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationException(
            f"Unsupported format: .{ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if file_size > MAX_FILE_SIZE:
        raise ValidationException(
            f"File too large: {file_size / 1024 / 1024:.1f}MB. Max: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )


async def upload_document(
    db: AsyncSession,
    kb_id: str,
    filename: str,
    content: bytes,
    file_size: int,
    minio=None,
) -> tuple[Document, str]:
    kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = kb_result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("Knowledge base not found")

    validate_file(filename, file_size)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    doc_id = str(uuid.uuid4())
    minio_key = f"{kb_id}/{doc_id}/{filename}"

    # Check for previous versions (same name in same KB)
    version = 1
    previous_version_id = None
    existing = await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id)
        .where(Document.original_name == filename)
        .order_by(Document.version.desc())
        .limit(1)
    )
    prev_doc = existing.scalar_one_or_none()
    if prev_doc:
        version = prev_doc.version + 1
        previous_version_id = prev_doc.id
        logger.info("Versioning: %s v%d (previous: %s v%d)", filename, version, prev_doc.id, prev_doc.version)

    if minio is not None:
        _put_object_with_retry(minio, app_settings.minio_bucket, minio_key, content, file_size)

    doc = Document(
        id=doc_id, kb_id=kb_id, filename=minio_key, original_name=filename,
        format=ext, file_size=file_size, minio_key=minio_key, status="pending",
        version=version, previous_version_id=previous_version_id,
    )

    db.add(doc)
    await db.execute(
        update(KnowledgeBase).where(KnowledgeBase.id == kb_id).values(
            document_count=KnowledgeBase.document_count + 1,
            updated_at=datetime.utcnow(),
        )
    )
    await db.flush()
    await db.refresh(doc)

    logger.info("Document uploaded | id=%s kb=%s name=%s size=%d", doc_id, kb_id, filename, file_size)
    return doc, kb.collection_name


async def delete_document(
    db: AsyncSession, milvus, doc_id: str, minio=None
) -> None:
    doc = await get_document(db, doc_id)

    kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id))
    kb = kb_result.scalar_one_or_none()

    if kb and milvus.has_collection(kb.collection_name):
        try:
            milvus.delete(collection_name=kb.collection_name, filter=f'doc_id == "{doc_id}"')
            logger.info("Deleted vectors for doc=%s from collection=%s", doc_id, kb.collection_name)
        except Exception as e:
            logger.warning("Failed to delete vectors for doc=%s: %s", doc_id, e)

    if minio is not None:
        try:
            minio.remove_object(app_settings.minio_bucket, doc.minio_key)
            logger.info("Deleted MinIO object: %s", doc.minio_key)
        except Exception as e:
            logger.warning("Failed to delete MinIO object %s: %s", doc.minio_key, e)

    await db.execute(
        update(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id).values(
            document_count=KnowledgeBase.document_count - 1,
            vector_count=KnowledgeBase.vector_count - doc.chunk_count,
            updated_at=datetime.utcnow(),
        )
    )
    await db.delete(doc)
    await db.flush()
    logger.info("Document deleted | id=%s name=%s", doc_id, doc.original_name)


async def update_document_status(
    db: AsyncSession, doc_id: str, status: str, error_message: str | None = None
):
    values = {"status": status}
    if status == "completed":
        values["processed_at"] = datetime.utcnow()
    if error_message:
        values["error_message"] = error_message

    await db.execute(update(Document).where(Document.id == doc_id).values(**values))
    await db.flush()

    if status == "failed":
        logger.error("Document processing failed | id=%s error=%s", doc_id, error_message)
    else:
        logger.info("Document status | id=%s status=%s", doc_id, status)
