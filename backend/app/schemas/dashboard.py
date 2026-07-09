from pydantic import BaseModel


class ServiceStatus(BaseModel):
    milvus: str
    postgres: str
    redis: str


class DashboardStats(BaseModel):
    total_knowledge_bases: int
    total_documents: int
    total_vectors: int
    avg_latency_ms: float
    services: ServiceStatus


class QualityTrendPoint(BaseModel):
    date: str
    avg_score: float
    search_count: int


class QualityMetrics(BaseModel):
    avg_score_7d: float
    avg_latency_7d: float
    total_searches_7d: int
    zero_result_rate: float
    trend: list[QualityTrendPoint]


class TopDocItem(BaseModel):
    doc_id: str
    doc_name: str
    kb_name: str
    search_count: int
    avg_score: float


class TopDocsResponse(BaseModel):
    items: list[TopDocItem]
