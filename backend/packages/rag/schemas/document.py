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
