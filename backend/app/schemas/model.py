from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ModelType(str, Enum):
    """Model type enumeration"""
    LLM = "llm"  # Large Language Model for chat/completion
    EMBEDDING = "embedding"  # Text embedding/vectorization
    RERANK = "rerank"  # Re-ranking model
    VISION = "vision"  # Image/video understanding
    SPEECH_TO_TEXT = "speech_to_text"  # Audio transcription
    TEXT_TO_SPEECH = "text_to_speech"  # Audio generation


class AdapterType(str, Enum):
    """Adapter/inference backend type"""
    LOCAL = "local"  # Local inference (sentence-transformers, transformers)
    API = "api"  # REST API (OpenAI-compatible, Anthropic, etc.)
    OLLAMA = "ollama"  # Ollama local server
    VLLM = "vllm"  # vLLM inference server
    TRITON = "triton"  # NVIDIA Triton
    CUSTOM = "custom"  # Custom endpoint


class ModelProvider(str, Enum):
    """Model provider enumeration"""
    # Open Source
    META = "meta"  # Llama series
    ALIBABA = "alibaba"  # Qwen series
    MISTRAL = "mistral"
    BAICHUAN = "baichuan"
    ZHIPU = "zhipu"
    MOONSHOT = "moonshot"
    LOCAL = "local"

    # Commercial APIs
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    AWS = "aws"

    # Embedding specific
    BAAI = "baai"  # Beijing Academy of AI
    SENTENCE_TRANSFORMERS = "sentence_transformers"

    # Rerank specific
    XEVA = "xeva"
    BAAI_RERANK = "baai_rerank"

    # Vision
    STABILITY = "stability"
    MIDJOURNEY = "midjourney"

    # Speech
    WHISPER = "whisper"
    AZURE_SPEECH = "azure_speech"
    ELEVENLABS = "elevenlabs"


class ModelStatus(str, Enum):
    """Model connection/status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    TESTING = "testing"


# ============================================================
# Model Configuration Schemas
# ============================================================

class ModelConfigBase(BaseModel):
    """Base model configuration"""
    name: str = Field(..., min_length=1, max_length=100, description="Model display name")
    model_id: str = Field(..., min_length=1, max_length=200, description="Model identifier/path")
    model_type: ModelType
    adapter_type: AdapterType
    provider: ModelProvider
    description: Optional[str] = Field(None, max_length=500)

    # Connection settings
    api_url: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = Field(None, max_length=500)

    # Model parameters
    max_tokens: Optional[int] = Field(None, ge=1)
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    frequency_penalty: Optional[float] = Field(None, ge=-2, le=2)
    presence_penalty: Optional[float] = Field(None, ge=-2, le=2)

    # Embedding specific
    embedding_dim: Optional[int] = Field(None, ge=1)
    normalization: bool = True

    # Runtime
    batch_size: Optional[int] = Field(None, ge=1)
    timeout_ms: int = 30000

    # Metadata - use field_validator to handle None from DB
    is_default: bool = False
    is_enabled: bool = True
    tags: Optional[list[str]] = None
    metadata: Optional[dict] = None

    def model_post_init(self, __context):
        # Handle None values from database
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}


class ModelConfigResponse(BaseModel):
    """Schema for model response"""
    # Basic info
    id: int
    name: str
    model_id: str
    model_type: str
    adapter_type: str
    provider: str
    description: Optional[str] = None

    # Connection settings
    api_url: Optional[str] = None
    api_key: Optional[str] = None

    # Model parameters
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None

    # Embedding specific
    embedding_dim: Optional[int] = None
    normalization: bool = True

    # Runtime
    batch_size: Optional[int] = None
    timeout_ms: int = 30000

    # Status
    status: ModelStatus = ModelStatus.INACTIVE
    last_tested_at: Optional[datetime] = None

    # Flags
    is_default: bool = False
    is_enabled: bool = True

    # Metadata - convert from DB
    tags: list[str] = []
    metadata: dict = {}

    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj):
        # Handle SQLAlchemy model conversion
        values = {
            "id": obj.id,
            "name": obj.name,
            "model_id": obj.model_id,
            "model_type": obj.model_type,
            "adapter_type": obj.adapter_type,
            "provider": obj.provider,
            "description": obj.description,
            "api_url": obj.api_url,
            "api_key": obj.api_key,
            "max_tokens": obj.max_tokens,
            "temperature": obj.temperature,
            "top_p": obj.top_p,
            "frequency_penalty": obj.frequency_penalty,
            "presence_penalty": obj.presence_penalty,
            "embedding_dim": obj.embedding_dim,
            "normalization": obj.normalization,
            "batch_size": obj.batch_size,
            "timeout_ms": obj.timeout_ms,
            "status": obj.status,
            "last_tested_at": obj.last_tested_at,
            "is_default": obj.is_default,
            "is_enabled": obj.is_enabled,
            "tags": obj.tags_list if hasattr(obj, 'tags_list') else [],
            "metadata": obj.metadata_json if obj.metadata_json else {},
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**values)


class ModelConfigCreate(ModelConfigBase):
    """Schema for creating a model"""
    pass


class ModelConfigUpdate(BaseModel):
    """Schema for updating a model (all fields optional)"""
    name: Optional[str] = None
    model_id: Optional[str] = None
    adapter_type: Optional[AdapterType] = None
    provider: Optional[ModelProvider] = None
    description: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None  # Empty string means "don't change"
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    embedding_dim: Optional[int] = None
    normalization: Optional[bool] = None
    batch_size: Optional[int] = None
    timeout_ms: Optional[int] = None
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict] = None


class ModelConfigList(BaseModel):
    """Schema for model list response"""
    items: list[ModelConfigResponse]
    total: int


# ============================================================
# Model Test Connection
# ============================================================

class ModelTestRequest(BaseModel):
    """Request to test model connection"""
    test_input: Optional[str] = None  # Custom test input


class ModelTestResult(BaseModel):
    """Result of model connection test"""
    success: bool
    message: str
    latency_ms: Optional[float] = None
    output_sample: Optional[str] = None


# ============================================================
# Model Presets (for quick setup)
# ============================================================

class ModelPreset(BaseModel):
    """Pre-configured model template"""
    id: str
    name: str
    description: str
    model_type: ModelType
    adapter_type: AdapterType
    provider: ModelProvider
    model_id: str
    default_config: dict
    recommended_for: list[str]  # Use cases


# Common model presets
COMMON_PRESETS: list[ModelPreset] = [
    # LLM Presets
    ModelPreset(
        id="qwen-72b",
        name="Qwen2.5-72B",
        description="Alibaba's flagship 72B model with strong reasoning",
        model_type=ModelType.LLM,
        adapter_type=AdapterType.VLLM,
        provider=ModelProvider.ALIBABA,
        model_id="Qwen/Qwen2.5-72B-Instruct",
        default_config={"max_tokens": 4096, "temperature": 0.7},
        recommended_for=["chat", "reasoning", "code"],
    ),
    ModelPreset(
        id="llama-3-70b",
        name="Llama-3-70B",
        description="Meta's powerful open model",
        model_type=ModelType.LLM,
        adapter_type=AdapterType.OLLAMA,
        provider=ModelProvider.META,
        model_id="llama3.1:70b",
        default_config={"max_tokens": 4096, "temperature": 0.7},
        recommended_for=["chat", "general"],
    ),
    ModelPreset(
        id="gpt-4o",
        name="GPT-4o",
        description="OpenAI's multimodal flagship",
        model_type=ModelType.LLM,
        adapter_type=AdapterType.API,
        provider=ModelProvider.OPENAI,
        model_id="gpt-4o",
        default_config={"max_tokens": 4096, "temperature": 0.7},
        recommended_for=["chat", "vision", "reasoning"],
    ),

    # Embedding Presets
    ModelPreset(
        id="bge-m3",
        name="BGE-M3",
        description="BAAI's multilingual embedding model",
        model_type=ModelType.EMBEDDING,
        adapter_type=AdapterType.LOCAL,
        provider=ModelProvider.BAAI,
        model_id="BAAI/bge-m3",
        default_config={"embedding_dim": 1024, "normalization": True},
        recommended_for=["multilingual", "retrieval"],
    ),
    ModelPreset(
        id="text-embedding-3-large",
        name="text-embedding-3-large",
        description="OpenAI's large embedding model",
        model_type=ModelType.EMBEDDING,
        adapter_type=AdapterType.API,
        provider=ModelProvider.OPENAI,
        model_id="text-embedding-3-large",
        default_config={"embedding_dim": 3072, "normalization": True},
        recommended_for=["high-accuracy", "english"],
    ),

    # Rerank Presets
    ModelPreset(
        id="bge-reranker-v2-m3",
        name="bge-reranker-v2-m3",
        description="BAAI's reranking model",
        model_type=ModelType.RERANK,
        adapter_type=AdapterType.LOCAL,
        provider=ModelProvider.BAAI_RERANK,
        model_id="BAAI/bge-reranker-v2-m3",
        default_config={"top_n": 10},
        recommended_for=["reranking", "multilingual"],
    ),
    ModelPreset(
        id="qwen-rerank",
        name="Qwen3-Rerank",
        description="Alibaba's reranking model",
        model_type=ModelType.RERANK,
        adapter_type=AdapterType.LOCAL,
        provider=ModelProvider.ALIBABA,
        model_id="Qwen/Qwen3-Rerank",
        default_config={"top_n": 10},
        recommended_for=["reranking", "chinese"],
    ),
]
