import logging
from fastapi import APIRouter, Query, UploadFile, File, BackgroundTasks, HTTPException

from app.core.deps import DBSession, MilvusDep
from app.config import settings as app_settings
from app.services import document_service
from app.schemas.document import (
    DocumentResponse, DocumentDetailResponse, DocumentListResponse,
    DocumentUpdateRequest, UploadResponse, ChunkPreviewRequest, ChunkPreviewResponse,
)

logger = logging.getLogger("app.api.documents")
router = APIRouter(prefix="/documents", tags=["documents"])


def _get_minio():
    try:
        from app.core.minio_client import get_minio_client
        return get_minio_client()
    except Exception as e:
        logger.warning("MinIO client unavailable: %s", e)
        return None


@router.get("", response_model=DocumentListResponse)
async def list_docs(
    db: DBSession,
    kb_id: str | None = Query(default=None),
    search: str = Query(default=""),
    category: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    items = await document_service.list_documents(db, kb_id, search, category, tag)
    cat_list = await document_service.get_categories(db, kb_id)
    return DocumentListResponse(items=items, total=len(items), categories=cat_list)


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    db: DBSession, milvus: MilvusDep,
    file: UploadFile = File(...), kb_id: str = Query(...),
):
    content = await file.read()
    doc, _ = await document_service.upload_document(
        db, kb_id, file.filename or "unknown", content, len(content), minio=_get_minio()
    )
    # Always commit and process the document
    await db.commit()
    try:
        from app.workers.document_pipeline import process_document
        result = await process_document({}, doc.id)
        logger.info("Document processed inline | doc_id=%s result=%s", doc.id, result)
        status = result.get("status", "completed") if result else "completed"
    except Exception:
        logger.exception("Processing failed | doc_id=%s", doc.id)
        status = "failed"
    await db.begin()

    return UploadResponse(
        id=doc.id, status=status,
        message=f"Uploaded and processed (chunks: {result.get('chunks', 'N/A')})" if result and status == "completed" else "Uploaded but processing failed",
    )


@router.post("/batch-upload", response_model=list[UploadResponse], status_code=201)
async def batch_upload_documents(
    db: DBSession, milvus: MilvusDep,
    files: list[UploadFile] = File(...), kb_id: str = Query(...),
):
    results = []
    for file in files:
        content = await file.read()
        doc, _ = await document_service.upload_document(
            db, kb_id, file.filename or "unknown", content, len(content), minio=_get_minio()
        )
        await db.commit()
        try:
            from app.workers.document_pipeline import process_document
            result = await process_document({}, doc.id)
            logger.info("Document processed inline | doc_id=%s result=%s", doc.id, result)
            status = result.get("status", "completed") if result else "completed"
        except Exception:
            logger.exception("Processing failed | doc_id=%s", doc.id)
            status = "failed"
        await db.begin()
        results.append(UploadResponse(
            id=doc.id, status=status,
            message="Uploaded and processed.",
        ))
    return results


@router.get("/failed", response_model=DocumentListResponse)
async def list_failed_documents(
    db: DBSession,
    kb_id: str | None = Query(default=None),
):
    """List all failed documents for a knowledge base."""
    from sqlalchemy import select
    from app.models.document import Document

    stmt = select(Document).where(Document.status == "failed").order_by(Document.uploaded_at.desc())
    if kb_id:
        stmt = stmt.where(Document.kb_id == kb_id)

    result = await db.execute(stmt)
    docs = result.scalars().all()

    items = [
        DocumentResponse(
            id=doc.id, kb_id=doc.kb_id, name=doc.original_name,
            format=doc.format, file_size=doc.file_size,
            status=doc.status, error_message=doc.error_message,
            uploaded_at=doc.uploaded_at, processed_at=doc.processed_at,
            chunk_count=doc.chunk_count, category=doc.category or "",
            tags=doc.tags_list,
        )
        for doc in docs
    ]

    return DocumentListResponse(items=items, total=len(items), categories=[])


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document(db: DBSession, doc_id: str):
    doc = await document_service.get_document(db, doc_id)
    preview = (doc.parsed_text or "")[:2000] if doc.parsed_text else None
    return DocumentDetailResponse(
        id=doc.id, kb_id=doc.kb_id, name=doc.original_name, format=doc.format,
        file_size=doc.file_size, status=doc.status, error_message=doc.error_message,
        uploaded_at=doc.uploaded_at, processed_at=doc.processed_at,
        chunk_count=doc.chunk_count, category=doc.category or "",
        tags=doc.tags_list, preview_text=preview,
        version=doc.version, previous_version_id=doc.previous_version_id,
    )


@router.post("/preview-chunks", response_model=ChunkPreviewResponse)
async def preview_chunks(data: ChunkPreviewRequest):
    """Preview how a document will be chunked (without storing)."""
    from app.core.rag_config import get_chunking_config
    from app.services.chunking_service import chunk_text

    cfg = get_chunking_config()
    chunks = chunk_text(
        data.content,
        strategy=cfg.get("strategy", "semantic"),
        chunk_size=cfg.get("chunk_size", 512),
        chunk_overlap=cfg.get("chunk_overlap", 50),
        separators=cfg.get("separators"),
    )

    sizes = [len(c.text) for c in chunks]
    return ChunkPreviewResponse(
        total_chunks=len(chunks),
        avg_chunk_size=sum(sizes) // len(sizes) if sizes else 0,
        min_chunk_size=min(sizes) if sizes else 0,
        max_chunk_size=max(sizes) if sizes else 0,
        preview=[c.text[:300] for c in chunks[:5]],
    )


@router.get("/{doc_id}/versions", response_model=list[DocumentResponse])
async def get_document_versions(db: DBSession, doc_id: str):
    """Get all versions of a document (version history chain)."""
    versions = []
    current = await document_service.get_document(db, doc_id)
    while current:
        versions.append(DocumentResponse(
            id=current.id, kb_id=current.kb_id, name=current.original_name,
            format=current.format, file_size=current.file_size,
            status=current.status, error_message=current.error_message,
            uploaded_at=current.uploaded_at, processed_at=current.processed_at,
            chunk_count=current.chunk_count, category=current.category or "",
            tags=current.tags_list,
        ))
        if current.previous_version_id:
            current = await document_service.get_document(db, current.previous_version_id)
        else:
            break
    return versions


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document_metadata(db: DBSession, doc_id: str, data: DocumentUpdateRequest):
    """Update document category and tags"""
    update_data = {}
    if data.category is not None:
        update_data["category"] = data.category
    if data.tags is not None:
        update_data["tags"] = data.tags
    doc = await document_service.update_document_metadata(db, doc_id, update_data)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(
        id=doc.id, kb_id=doc.kb_id, name=doc.original_name, format=doc.format,
        file_size=doc.file_size, status=doc.status, error_message=doc.error_message,
        uploaded_at=doc.uploaded_at, processed_at=doc.processed_at,
        chunk_count=doc.chunk_count, category=doc.category or "",
        tags=doc.tags_list,
    )


@router.post("/{doc_id}/reprocess", response_model=dict)
async def reprocess_document(
    db: DBSession,
    doc_id: str,
    force: bool = Query(default=False, description="Force reprocess even if status is completed"),
):
    """
    Reprocess a document (useful for failed documents).

    - Only documents with status='failed' or status='pending' can be reprocessed by default
    - Use `force=true` to reprocess completed documents (e.g., after changing chunking strategy)
    """
    doc = await document_service.get_document(db, doc_id)

    # Check if document can be reprocessed
    if doc.status not in ("failed", "pending") and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Document status is '{doc.status}'. Use force=true to reprocess completed documents."
        )

    # Reset status to pending
    await document_service.update_document_status(db, doc_id, "pending")
    await db.commit()

    # Reprocess
    from app.workers.document_pipeline import process_document
    result = await process_document({}, doc_id)

    return {
        "doc_id": doc_id,
        "previous_status": doc.status,
        "result": result,
        "message": "Reprocessed successfully" if result and result.get("status") == "completed" else "Reprocess failed",
    }


@router.post("/batch-reprocess", response_model=dict)
async def batch_reprocess_documents(
    db: DBSession,
    kb_id: str = Query(..., description="Knowledge base ID"),
    failed_only: bool = Query(default=True, description="Only reprocess failed documents"),
    doc_ids: list[str] = Query(default=None, description="Specific document IDs to reprocess"),
):
    """
    Batch reprocess multiple documents.

    - `failed_only=true`: Only reprocess documents with status='failed'
    - `doc_ids`: If provided, reprocess only these specific documents
    """
    from sqlalchemy import select
    from app.models.document import Document

    # Build query
    stmt = select(Document).where(Document.kb_id == kb_id)

    if doc_ids:
        stmt = stmt.where(Document.id.in_(doc_ids))
    elif failed_only:
        stmt = stmt.where(Document.status == "failed")

    result = await db.execute(stmt)
    docs = result.scalars().all()

    if not docs:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "message": "No documents to reprocess",
        }

    # Reprocess each document
    success_count = 0
    failed_count = 0
    results = []

    for doc in docs:
        try:
            # Reset status
            await document_service.update_document_status(db, doc.id, "pending")
            await db.commit()

            # Process
            from app.workers.document_pipeline import process_document
            result = await process_document({}, doc.id)

            if result and result.get("status") == "completed":
                success_count += 1
                results.append({"doc_id": doc.id, "status": "success", "chunks": result.get("chunks")})
            else:
                failed_count += 1
                results.append({"doc_id": doc.id, "status": "failed", "error": result})

        except Exception as e:
            failed_count += 1
            results.append({"doc_id": doc.id, "status": "failed", "error": str(e)})
            logger.exception("Batch reprocess failed | doc_id=%s", doc.id)
            await db.rollback()
            continue

        await db.begin()

    return {
        "total": len(docs),
        "success": success_count,
        "failed": failed_count,
        "results": results,
        "message": f"Reprocessed {success_count}/{len(docs)} documents successfully",
    }


@router.delete("/{doc_id}", status_code=204)
async def delete_document(db: DBSession, milvus: MilvusDep, doc_id: str):
    await document_service.delete_document(db, milvus, doc_id, minio=_get_minio())
