from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class ModelSettings(BaseModel):
    # References to model_configs table by ID
    default_embedding_model_id: int | None = None
    default_rerank_model_id: int | None = None
    default_llm_model_id: int | None = None

    # Legacy fields for backward compatibility (will be deprecated)
    embedding_provider: str = "local"
    embedding_model: str = "BGE-M3"
    embedding_dim: int = 1024
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    rerank_model: str = "Qwen3-Rerank"
    llm_model: str = "Qwen2.5-72B"


class ChunkingSettings(BaseModel):
    strategy: str = "recursive"  # recursive, fixed, semantic, agentic, small_to_big, parent_child, markdown, code
    chunk_size: int = 512
    chunk_overlap: int = 50
    separators: list[str] = ["\n\n", "\n", ".", " ", ""]
    # For parent_child strategy
    parent_chunk_size: int | None = None  # Defaults to chunk_size * 2

    # 文件类型路由配置（系统级默认策略）
    # 格式：{"pdf": {"strategy": "semantic", "chunk_size": 512, "chunk_overlap": 0.2}, ...}
    file_type_routes: dict[str, dict] = Field(default_factory=dict)


class RetrievalDefaults(BaseModel):
    default_top_k: int = 10
    default_min_score: float = 0.6
    enable_rerank: bool = True
    rerank_top_n: int = 3


class SecuritySettings(BaseModel):
    max_upload_size_mb: int = 50
    allowed_formats: list[str] = ["pdf", "docx", "txt", "md", "html"]
    rate_limit_per_minute: int = 100
    search_timeout_ms: int = 5000
    log_retention_days: int = 30


class SettingsObject(BaseModel):
    model: ModelSettings = Field(default_factory=ModelSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    retrieval: RetrievalDefaults = Field(default_factory=RetrievalDefaults)
    security: SecuritySettings = Field(default_factory=SecuritySettings)


class SettingsUpdateRequest(BaseModel):
    model: ModelSettings | None = None
    chunking: ChunkingSettings | None = None
    retrieval: RetrievalDefaults | None = None
    security: SecuritySettings | None = None


class SettingsResponse(BaseModel):
    version: int
    is_active: bool
    settings: SettingsObject
    published_at: datetime | None = None


class SettingsHistoryItem(BaseModel):
    version: int
    action: str
    changed_by: str
    settings_json: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
