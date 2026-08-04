"""
同义词管理 API
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.rag.services.synonym_service import SynonymService, init_default_synonyms

router = APIRouter(prefix="/synonyms", tags=["synonyms"])


class SynonymCreate(BaseModel):
    """创建同义词"""
    standard_term: str = Field(..., min_length=1, description="标准词")
    synonyms: List[str] = Field(default_factory=list, description="同义词列表")
    category: Optional[str] = Field(None, description="分类")
    kb_id: Optional[str] = Field(None, description="知识库 ID")


class SynonymUpdate(BaseModel):
    """更新同义词"""
    standard_term: str = Field(..., min_length=1, description="标准词")
    synonyms: List[str] = Field(default_factory=list, description="同义词列表")
    category: Optional[str] = Field(None, description="分类")
    kb_id: Optional[str] = Field(None, description="知识库 ID")
    is_enabled: bool = True


class SynonymResponse(BaseModel):
    """同义词响应"""
    id: int
    standard_term: str
    synonyms: List[str]
    category: Optional[str]
    kb_id: Optional[str]
    is_enabled: bool

    class Config:
        from_attributes = True


@router.post("", response_model=SynonymResponse)
async def create_synonym(
    data: SynonymCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的同义词映射"""
    service = SynonymService(db)
    entry = await service.add_synonym(
        standard_term=data.standard_term,
        synonyms=data.synonyms,
        category=data.category,
        kb_id=data.kb_id,
    )
    return entry


@router.get("", response_model=List[SynonymResponse])
async def list_synonyms(
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    category: Optional[str] = Query(None, description="分类"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取同义词列表"""
    service = SynonymService(db)
    entries = await service.list_synonyms(kb_id=kb_id, category=category)
    return entries


@router.put("/{synonym_id}", response_model=SynonymResponse)
async def update_synonym(
    synonym_id: int,
    data: SynonymUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新同义词"""
    service = SynonymService(db)
    from sqlalchemy import update
    from packages.rag.models.synonym import Synonym
    import json

    # Check if exists
    result = await db.execute(
        update(Synonym)
        .where(Synonym.id == synonym_id)
        .values(
            standard_term=data.standard_term,
            synonyms_json=json.dumps(data.synonyms, ensure_ascii=False),
            category=data.category,
            kb_id=data.kb_id,
            is_enabled=data.is_enabled,
        )
    )
    await db.commit()

    # Fetch updated entry
    entry = await service.list_synonyms()
    synonym = next((s for s in entry if s.id == synonym_id), None)
    if not synonym:
        raise HTTPException(status_code=404, detail="Synonym not found")
    return synonym


@router.delete("/{synonym_id}")
async def delete_synonym(
    synonym_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除同义词"""
    service = SynonymService(db)
    success = await service.remove_synonym(synonym_id)
    if not success:
        raise HTTPException(status_code=404, detail="Synonym not found")
    return {"message": "Synonym deleted"}


@router.post("/init")
async def init_synonyms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """初始化默认同义词库"""
    await init_default_synonyms(db)
    return {"message": "Default synonyms initialized"}


@router.get("/expand/{query}")
async def expand_query(
    query: str,
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """扩展查询关键词（获取同义词）"""
    service = SynonymService(db)
    expanded = await service.expand_query(query, kb_id=kb_id)
    return {
        "original": query,
        "expanded": expanded,
        "count": len(expanded),
    }
