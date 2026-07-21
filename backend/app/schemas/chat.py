"""
Chat completion schemas
"""
from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """RAG-grounded chat completion request"""
    query: str = Field(..., description="User's question")
    kb_ids: list[str] = Field(default_factory=list, description="Knowledge base IDs to search")
    session_id: Optional[str] = Field(None, description="Conversation session ID for multi-turn")
    top_k: int = Field(5, ge=1, le=50, description="Number of chunks to retrieve")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="Minimum relevance score")
    enable_rerank: bool = Field(True, description="Enable cross-encoder reranking")
    enable_hybrid: bool = Field(False, description="Enable hybrid search (dense + sparse)")
    enable_expansion: bool = Field(True, description="Enable query expansion (HyDE)")
    stream: bool = Field(False, description="Enable SSE streaming response")


class CitationInfo(BaseModel):
    """Citation reference"""
    index: int
    doc_name: str
    chunk_id: str
    content_type: str = "text"


class ChatResponse(BaseModel):
    """RAG-grounded chat completion response"""
    answer: str
    reasoning: str = ""
    citations: list[CitationInfo] = Field(default_factory=list)
    hallu_score: Optional[int] = None
    chunks_used: int = 0


class ChatStreamEvent(BaseModel):
    """SSE stream event"""
    type: str = Field(..., description="Event type: chunk | citation | done")
    content: Optional[str] = None
    citations: Optional[list[CitationInfo]] = None
    hallu_score: Optional[int] = None
