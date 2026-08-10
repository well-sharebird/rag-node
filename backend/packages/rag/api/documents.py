import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, UploadFile, File, BackgroundTasks, HTTPException
from pydantic import BaseModel

from packages.core.deps import DBSession, MilvusDep
from packages.core.config import settings as app_settings
from packages.rag.services import document_service
from packages.rag.schemas.document import (
    DocumentResponse, DocumentDetailResponse, DocumentListResponse,
    DocumentUpdateRequest, UploadResponse, ChunkPreviewRequest, ChunkPreviewResponse,
    PipelineResponse, PipelineStage, InputSummary, OutputSummary, ErrorInfo,
)

logger = logging.getLogger("app.api.documents")
router = APIRouter(prefix="/documents", tags=["documents"])


def _get_minio():
    try:
        from packages.core.infra.minio_client import get_minio_client
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
    db: DBSession,
    file: UploadFile = File(...), kb_id: str = Query(...),
):
    """
    上传文档并启动后台异步处理

    流程：
    1. 上传文件到 MinIO
    2. 创建文档记录（status=pending, progress=0）
    3. 启动后台任务异步处理
    4. 立即返回，前端轮询进度
    """
    content = await file.read()
    doc, _ = await document_service.upload_document(
        db, kb_id, file.filename or "unknown", content, len(content), minio=_get_minio()
    )
    await db.commit()

    # 启动后台异步任务处理文档
    asyncio.create_task(process_document_background(str(doc.id)))
    logger.info("Document background task started | doc_id=%s", doc.id)

    return UploadResponse(
        id=doc.id, status="pending",
        message="Document uploaded, processing in background",
    )


async def process_document_background(doc_id: str):
    """在后台异步处理文档，不阻塞 API 响应。"""
    from packages.core.database import async_session_factory
    from packages.rag.workers.document_pipeline import process_document
    from sqlalchemy import update
    from packages.rag.models.document import Document

    try:
        async with async_session_factory() as session:
            result = await process_document(session, doc_id)

            # 更新文档状态
            if result and result.get("status") == "completed":
                await session.execute(
                    update(Document).where(Document.id == doc_id).values(
                        status="completed",
                        chunk_count=result.get("chunks", 0)
                    )
                )
            else:
                await session.execute(
                    update(Document).where(Document.id == doc_id).values(status="failed")
                )
            await session.commit()

            logger.info("Document background processing completed | doc_id=%s result=%s", doc_id, result)

    except Exception as e:
        logger.exception("Document background processing failed | doc_id=%s", doc_id)
        # 更新失败状态
        async with async_session_factory() as session:
            await session.execute(
                update(Document).where(Document.id == doc_id).values(
                    status="failed",
                    error_message=f"{type(e).__name__}: {e}"
                )
            )
            await session.commit()


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
            from packages.rag.workers.document_pipeline import process_document
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
    from packages.rag.models.document import Document

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
    from packages.rag.config import get_chunking_config
    from packages.rag.services.chunking_service import chunk_text

    cfg = get_chunking_config()
    chunks = await chunk_text(
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


@router.get("/{doc_id}/pipeline", response_model=PipelineResponse)
async def get_document_pipeline(db: DBSession, doc_id: str):
    """
    获取文档处理流水线追踪详情

    返回文档处理的各个阶段信息，包括输入输出数据摘要
    """
    from sqlalchemy import select
    from packages.rag.models.document import Document

    # 获取文档信息
    doc = await document_service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 获取关联的 trace_id (从 metadata_json 或单独存储)
    trace_id = None
    if doc.metadata_json:
        import json
        try:
            metadata = json.loads(doc.metadata_json) if isinstance(doc.metadata_json, str) else doc.metadata_json
            trace_id = metadata.get("trace_id")
        except:
            pass

    # 如果没有 trace_id，返回空流水线
    if not trace_id:
        return PipelineResponse(
            document_id=doc_id,
            stages=[],
            total_duration_ms=0,
            status=doc.status,
        )

    # 从 Elasticsearch 获取追踪数据
    try:
        from packages.core.infra.es_client import get_es_client
        es = get_es_client()

        # 查询该 trace 的所有 spans
        search_query = {
            "query": {"term": {"trace_id": trace_id}},
            "sort": [{"started_at": "asc"}]
        }

        response = await es.search(index="execution_traces", body=search_query)
        spans = [hit["_source"] for hit in response["hits"]["hits"]]

        # 转换为流水线阶段
        stages = []
        stage_order = ["parsing", "cleaning", "desensitization", "chunking", "embedding", "indexing"]

        for stage_key in stage_order:
            stage_spans = [s for s in spans if stage_key in s.get("node_type", "").lower()]
            if not stage_spans:
                continue

            span = stage_spans[0]
            duration = span.get("duration_ms", 0)
            # 映射 ES 的 status 到前端期望的值
            es_status = span.get("status", "unknown")
            status = "completed" if es_status == "success" else es_status

            # 提取输入输出摘要
            input_data = span.get("input_data", {})
            output_data = span.get("output_data", {})

            # 提取 input preview（跳过二进制数据）
            input_preview = ""
            if input_data:
                if "preview" in input_data:
                    val = str(input_data["preview"])
                    # 跳过二进制数据（包含 PK 头、\x 转义等）
                    if not (val.startswith("b'") or "\\x" in val or val.startswith("PK")):
                        input_preview = val[:200]
                if not input_preview and "args" in input_data:
                    args = input_data.get("args", [])
                    # 找第一个文本参数（跳过二进制）
                    for arg in args:
                        arg_str = str(arg)
                        if not (arg_str.startswith("b'") or "\\x" in arg_str or arg_str.startswith("PK")):
                            # 只保留可打印字符
                            clean = "".join(c for c in arg_str if c.isprintable() or c in " \n\t")
                            if len(clean) > 10:
                                input_preview = clean[:200]
                                break
                if not input_preview and "kwargs" in input_data:
                    kwargs = input_data.get("kwargs", {})
                    # 提取有意义的 kwargs
                    text_parts = []
                    for k, v in kwargs.items():
                        if k not in ("strategy", "chunk_size", "chunk_overlap"):
                            text_parts.append(f"{k}={v}")
                    input_preview = ", ".join(text_parts)[:200] if text_parts else ""

            # 提取 output preview
            output_preview = ""
            output_count = None
            if output_data:
                if "preview" in output_data:
                    val = output_data["preview"]
                    if isinstance(val, list):
                        # 列表预览（如 chunks）
                        output_preview = f"[{len(val)} 项] " + str(val[0])[:150] if val else ""
                    elif isinstance(val, str):
                        output_preview = val[:200]
                    else:
                        output_preview = str(val)[:200]
                    output_count = output_data.get("length") or output_data.get("count")
                elif "result" in output_data:
                    result = output_data.get("result", "")
                    if isinstance(result, str):
                        # 清理不可打印字符
                        clean = "".join(c for c in result if c.isprintable() or c in " \n\t")
                        output_preview = clean[:200]
                    else:
                        output_preview = str(result)[:200]

            stages.append(PipelineStage(
                stage=stage_key,
                label=stage_key.title(),
                status=status,
                duration_ms=duration,
                input_summary=InputSummary(
                    preview=input_preview,
                    count=input_data.get("args_count") or input_data.get("count"),
                    size=input_data.get("size"),
                ),
                output_summary=OutputSummary(
                    preview=output_preview,
                    count=output_count,
                    size=output_data.get("size"),
                ),
                error=ErrorInfo(
                    message=span.get("error_info", {}).get("message", ""),
                    details=span.get("error_info", {}),
                ) if status == "failed" else None,
                span_id=span.get("span_id", ""),
            ))

        total_duration = sum(s.duration_ms or 0 for s in stages)

        return PipelineResponse(
            document_id=doc_id,
            stages=stages,
            total_duration_ms=total_duration,
            status=doc.status,
        )

    except Exception as e:
        logger.warning("Failed to get pipeline data: %s", e)
        # 返回空结果但不报错
        return PipelineResponse(
            document_id=doc_id,
            stages=[],
            total_duration_ms=0,
            status=doc.status,
        )


@router.get("/{doc_id}/stages/{stage}/data")
async def get_stage_data(db: DBSession, doc_id: str, stage: str):
    """获取指定阶段的详细输入输出数据"""
    from sqlalchemy import select
    from packages.rag.models.document import Document

    doc = await document_service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    trace_id = None
    if doc.metadata_json:
        import json
        try:
            metadata = json.loads(doc.metadata_json) if isinstance(doc.metadata_json, str) else doc.metadata_json
            trace_id = metadata.get("trace_id")
        except:
            pass
    if not trace_id:
        raise HTTPException(status_code=404, detail="No trace data found")

    try:
        from packages.core.infra.es_client import get_es_client
        es = get_es_client()

        # 查询指定阶段的 span
        search_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"trace_id": trace_id}},
                        {"match": {"node_type": stage}}
                    ]
                }
            }
        }

        response = await es.search(index="execution_traces", body=search_query)
        if not response["hits"]["hits"]:
            raise HTTPException(status_code=404, detail="Stage not found")

        span = response["hits"]["hits"][0]["_source"]

        return {
            "stage": stage,
            "input": span.get("input_data", {}),
            "output": span.get("output_data", {}),
            "metrics": {
                "duration_ms": span.get("duration_ms"),
                "items_in": span.get("input_data", {}).get("count"),
                "items_out": span.get("output_data", {}).get("count"),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get stage data")
        raise HTTPException(status_code=500, detail=str(e))


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
    from packages.rag.workers.document_pipeline import process_document
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
    from packages.rag.models.document import Document

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
            from packages.rag.workers.document_pipeline import process_document
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
    await db.commit()


class DocumentProgressResponse(BaseModel):
    """Document processing progress response"""
    doc_id: str
    status: str
    progress: int
    current_stage: Optional[str]
    chunk_count: Optional[int]
    error_message: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]


@router.get("/{doc_id}/progress", response_model=DocumentProgressResponse)
async def get_document_progress(db: DBSession, doc_id: str):
    """
    获取文档处理进度

    返回当前处理状态和进度百分比，用于前端实时展示
    """
    from sqlalchemy import select
    from packages.rag.models.document import Document

    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentProgressResponse(
        doc_id=str(doc.id),
        status=doc.status,
        progress=doc.progress,
        current_stage=doc.current_stage,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
    )
