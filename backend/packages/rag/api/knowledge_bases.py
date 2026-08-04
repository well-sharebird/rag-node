from __future__ import annotations
from fastapi import APIRouter, Query

from packages.core.deps import DBSession, MilvusDep
from packages.rag.services import kb_service
from packages.rag.schemas.knowledge_base import (
    KBCreateRequest,
    KBUpdateRequest,
    KBResponse,
    KBListResponse,
)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=KBListResponse)
async def list_kbs(db: DBSession, search: str = Query(default="")):
    items = await kb_service.list_knowledge_bases(db, search)
    return KBListResponse(
        items=[KBResponse.model_validate(kb) for kb in items],
        total=len(items),
    )


@router.post("", response_model=KBResponse, status_code=201)
async def create_kb(db: DBSession, milvus: MilvusDep, data: KBCreateRequest):
    kb = await kb_service.create_knowledge_base(db, milvus, data)
    return KBResponse.model_validate(kb)


@router.get("/{kb_id}", response_model=KBResponse)
async def get_kb(db: DBSession, kb_id: str):
    kb = await kb_service.get_knowledge_base(db, kb_id)
    return KBResponse.model_validate(kb)


@router.put("/{kb_id}", response_model=KBResponse)
async def update_kb(db: DBSession, kb_id: str, data: KBUpdateRequest):
    kb = await kb_service.update_knowledge_base(db, kb_id, data)
    return KBResponse.model_validate(kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(db: DBSession, milvus: MilvusDep, kb_id: str):
    await kb_service.delete_knowledge_base(db, milvus, kb_id)
