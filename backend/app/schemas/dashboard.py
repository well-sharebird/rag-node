from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    milvus: str
    postgres: str
    redis: str
    embedding: str = "unknown"
    doc_processor: str = "unknown"


class DashboardStats(BaseModel):
    total_knowledge_bases: int
    total_documents: int
    total_vectors: int
    avg_latency_ms: float
    services: ServiceStatus

    class Config:
        populate_by_name = True


class QualityTrendPoint(BaseModel):
    date: str
    avg_score: float
    search_count: int

    class Config:
        populate_by_name = True


class QualityMetrics(BaseModel):
    avg_score_7d: float
    avg_latency_7d: float
    total_searches_7d: int
    zero_result_rate: float
    trend: list[QualityTrendPoint]

    class Config:
        populate_by_name = True


class TopDocItem(BaseModel):
    doc_id: str = Field(..., alias="docId")
    doc_name: str = Field(..., alias="docName")
    kb_name: str = Field(..., alias="kbName")
    search_count: int = Field(..., alias="searchCount")
    avg_score: float = Field(..., alias="avgScore")

    class Config:
        populate_by_name = True


class TopDocsResponse(BaseModel):
    items: list[TopDocItem]

    class Config:
        populate_by_name = True
