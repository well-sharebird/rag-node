from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    permissions: str = Field(default="write", pattern="^(read|write|admin)$")
    # 检索配置 (可选，不设置则继承系统级配置)
    top_k: int | None = Field(None, ge=1, le=100)
    min_score: float | None = Field(None, ge=0.0, le=1.0)
    enable_rerank: bool | None = None


class KBUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    permissions: str | None = Field(None, pattern="^(read|write|admin)$")
    # 检索配置 (可选，不设置则继承系统级配置)
    top_k: int | None = Field(None, ge=1, le=100)
    min_score: float | None = Field(None, ge=0.0, le=1.0)
    enable_rerank: bool | None = None


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    vector_count: int
    permissions: str
    # 检索配置 (NULL 表示继承系统级配置)
    top_k: int | None
    min_score: float | None
    enable_rerank: bool | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBListResponse(BaseModel):
    items: list[KBResponse]
    total: int
