from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    permissions: str = Field(default="write", pattern="^(read|write|admin)$")


class KBUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    permissions: str | None = Field(None, pattern="^(read|write|admin)$")


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    vector_count: int
    permissions: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBListResponse(BaseModel):
    items: list[KBResponse]
    total: int
