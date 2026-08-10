from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    kb_id: str
    name: str
    format: str
    file_size: int
    status: str
    error_message: str | None = None
    uploaded_at: datetime
    processed_at: datetime | None = None
    kb_name: str | None = None
    chunk_count: int = 0
    category: str = ""
    tags: list[str] = []

    model_config = {"from_attributes": True}


class DocumentUpdateRequest(BaseModel):
    """Update document metadata (category, tags)"""
    category: str | None = None
    tags: list[str] | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    categories: list[str] = []  # Available category paths for filter


class UploadResponse(BaseModel):
    id: str
    status: str
    message: str


class DocumentDetailResponse(DocumentResponse):
    """Document detail with preview text and version info"""
    preview_text: str | None = None
    version: int = 1
    previous_version_id: str | None = None


class ChunkPreviewRequest(BaseModel):
    """Request to preview chunks for a document"""
    content: str  # Document text content


class ChunkPreviewResponse(BaseModel):
    """Chunk preview result"""
    total_chunks: int
    avg_chunk_size: int
    min_chunk_size: int
    max_chunk_size: int
    preview: list[str]  # First 5 chunks


# ============================================================
# Pipeline Tracking Schemas
# ============================================================

class InputSummary(BaseModel):
    """输入数据摘要"""
    preview: str = ""
    count: int | None = None
    size: int | None = None


class OutputSummary(BaseModel):
    """输出数据摘要"""
    preview: str = ""
    count: int | None = None
    size: int | None = None


class ErrorInfo(BaseModel):
    """错误信息"""
    message: str = ""
    details: dict = {}


class PipelineStage(BaseModel):
    """流水线处理阶段"""
    stage: str  # parsing, cleaning, desensitization, chunking, embedding, indexing
    label: str
    status: str  # pending, running, completed, failed
    duration_ms: int | None = None
    input_summary: InputSummary | None = None
    output_summary: OutputSummary | None = None
    error: ErrorInfo | None = None
    span_id: str = ""


class PipelineResponse(BaseModel):
    """文档处理流水线响应"""
    document_id: str
    stages: list[PipelineStage]
    total_duration_ms: int
    status: str  # completed, failed, running
