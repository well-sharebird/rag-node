"""
Chat completion schemas
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


# ============== Agent Schemas ==============

class AgentCreate(BaseModel):
    """创建 Agent 请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = None
    agent_type: Optional[str] = Field("single", pattern="^(single|multi)$")
    default_model_config: Optional[dict] = None
    system_prompt: str = Field(..., min_length=1)
    enabled_skills: Optional[list[str]] = None
    mcp_servers: Optional[list[str]] = None
    memory_type: Optional[str] = Field("conversation", pattern="^(conversation|vector|hybrid)$")
    memory_ttl_hours: Optional[int] = Field(24, ge=1)
    max_memory_turns: Optional[int] = Field(50, ge=1)
    kb_ids: Optional[list[str]] = None
    retrieval_top_k: Optional[int] = Field(5, ge=1, le=50)
    retrieval_enabled: Optional[bool] = False
    multi_agent_config: Optional[dict] = None
    is_public: Optional[bool] = Field(False, description="是否公开分享到广场")


class AgentUpdate(BaseModel):
    """更新 Agent 请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = None
    default_model_config: Optional[dict] = None
    system_prompt: Optional[str] = None
    enabled_skills: Optional[list[str]] = None
    mcp_servers: Optional[list[str]] = None
    memory_type: Optional[str] = None
    memory_ttl_hours: Optional[int] = None
    max_memory_turns: Optional[int] = None
    kb_ids: Optional[list[str]] = None
    retrieval_top_k: Optional[int] = None
    retrieval_enabled: Optional[bool] = None
    multi_agent_config: Optional[dict] = None
    is_public: Optional[bool] = None
    changelog: Optional[str] = None  # 版本更新说明


class AgentResponse(BaseModel):
    """Agent 响应"""
    id: UUID
    user_id: int
    name: str
    description: Optional[str]
    icon: Optional[str]
    agent_type: str
    default_model_config: Optional[dict]
    system_prompt: str
    enabled_skills: list[str]
    mcp_servers: list[str]
    memory_type: str
    memory_ttl_hours: int
    max_memory_turns: int
    kb_ids: list[str]
    retrieval_top_k: int
    retrieval_enabled: bool
    multi_agent_config: Optional[dict]
    status: str
    is_public: bool
    current_version: str
    total_runs: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class AgentListItem(BaseModel):
    """Agent 列表项"""
    id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    agent_type: str
    status: str
    is_public: bool
    current_version: str
    total_runs: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== Agent Runtime Schemas ==============

class ModelConfig(BaseModel):
    """运行时模型配置（由用户选择传递）"""
    provider: str = Field(..., description="模型供应商代码，如 anthropic, openai")
    model: str = Field(..., description="模型名称，如 claude-3-5-sonnet")
    temperature: Optional[float] = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(4096, ge=1)
    top_p: Optional[float] = Field(1.0, ge=0, le=1)
    api_key: Optional[str] = Field(None, description="API Key（可选，从数据库获取）")
    base_url: Optional[str] = Field(None, description="API 基础 URL（可选，从数据库获取）")


class AgentRunRequest(BaseModel):
    """Agent 运行请求"""
    agent_id: str
    query: str
    model: ModelConfig  # 运行时由用户选择模型
    session_id: Optional[str] = None  # 会话 ID，用于多轮对话
    stream: bool = False


class AgentRunResponse(BaseModel):
    """Agent 运行响应"""
    run_id: str
    agent_id: str
    response: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    session_id: Optional[str]


class AgentStreamEvent(BaseModel):
    """Agent 流式事件"""
    type: str  # token | done | error
    content: Optional[str] = None
    run_id: Optional[str] = None
    error: Optional[str] = None


# ============== Original Chat Schemas ==============

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
    model_id: Optional[str] = Field(None, description="Model ID to use for generation (optional, uses default if not specified)")


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
