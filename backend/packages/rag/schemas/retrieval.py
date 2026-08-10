from datetime import datetime
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    kb_id: str
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    enable_hybrid: bool = False
    enable_rerank: bool = False
    enable_multimodal: bool = False
    # Metadata filtering
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    doc_ids: list[str] | None = Field(default=None, description="Filter by specific document IDs")
    content_type: str | None = Field(default=None, description="Filter by content type: text/table/image")


class SearchResultItem(BaseModel):
    chunk_id: str
    content: str
    score: float
    metadata: dict
    content_type: str = "text"


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    query: str
    search_time_ms: float
    total_recalled: int


class SearchHistoryItem(BaseModel):
    query: str
    kb_name: str
    result_count: int
    latency_ms: float
    created_at: str


class SearchHistoryResponse(BaseModel):
    items: list[SearchHistoryItem]
    total: int
