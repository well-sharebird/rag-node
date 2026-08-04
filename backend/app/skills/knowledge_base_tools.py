"""
知识库管理 Skill
提供知识库创建、查询、文档管理等工具
"""
import logging
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.services.kb_service import (
    list_knowledge_bases as kb_service_list,
    get_knowledge_base as kb_service_get,
    create_knowledge_base as kb_service_create,
    delete_knowledge_base as kb_service_delete,
)
from app.services.document_service import (
    list_documents as doc_service_list,
    delete_document as doc_service_delete,
)

logger = logging.getLogger("app.skills.knowledge_base")

# ========== 系统提示词 ==========
KB_TOOL_PROMPT = """你是知识库管理专家，可以帮用户执行以下操作：

## 可用工具
1. **list_knowledge_bases** - 获取知识库列表
2. **get_knowledge_base** - 获取知识库详情
3. **create_knowledge_base** - 创建新知识库
4. **delete_knowledge_base** - 删除知识库
5. **list_documents** - 获取知识库中的文档列表
6. **delete_document** - 删除文档

## 使用场景
- 用户问"有哪些知识库" → 调用 list_knowledge_bases
- 用户问"XX 知识库里有什么" → 调用 list_documents
- 用户要创建知识库 → 调用 create_knowledge_base
- 用户要删除内容 → 调用 delete_knowledge_base 或 delete_document

## 输出规范
- 列表类操作：简洁展示名称和关键信息
- 详情类操作：结构化展示完整信息
- 操作类操作：返回成功/失败状态和影响
"""


# ========== 输入输出 Schema ==========

class ListKBInput(BaseModel):
    """获取知识库列表"""
    search: Optional[str] = Field(None, description="搜索关键词")


class ListKBOutput(BaseModel):
    """知识库列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class GetKBInput(BaseModel):
    """获取知识库详情"""
    kb_id: str = Field(..., description="知识库 ID")


class GetKBOutput(BaseModel):
    """知识库详情输出"""
    success: bool
    kb_info: Optional[dict] = None
    message: str = ""


class CreateKBInput(BaseModel):
    """创建知识库"""
    name: str = Field(..., description="知识库名称", max_length=100)
    description: str = Field("", description="知识库描述")


class CreateKBOutput(BaseModel):
    """创建知识库输出"""
    success: bool
    kb_id: Optional[str] = None
    kb_name: Optional[str] = None
    message: str = ""


class DeleteKBInput(BaseModel):
    """删除知识库"""
    kb_id: str = Field(..., description="知识库 ID")


class DeleteKBOutput(BaseModel):
    """删除知识库输出"""
    success: bool
    message: str = ""


class ListDocsInput(BaseModel):
    """获取文档列表"""
    kb_id: str = Field(..., description="知识库 ID")


class ListDocsOutput(BaseModel):
    """文档列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class DeleteDocInput(BaseModel):
    """删除文档"""
    doc_id: str = Field(..., description="文档 ID")


class DeleteDocOutput(BaseModel):
    """删除文档输出"""
    success: bool
    message: str = ""


# ========== 工具函数 ==========

async def list_knowledge_bases(
    db: AsyncSession,
    user_id: int,
    search: Optional[str] = None,
) -> ListKBOutput:
    """获取知识库列表"""
    try:
        kbs = await kb_service_list(db, search or "")
        items = [{
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "document_count": getattr(kb, "document_count", 0),
        } for kb in kbs]

        return ListKBOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个知识库",
        )
    except Exception as e:
        logger.error(f"Failed to list knowledge bases: {e}")
        return ListKBOutput(success=False, message=f"获取失败：{str(e)}")


async def get_knowledge_base(
    db: AsyncSession,
    kb_id: str,
) -> GetKBOutput:
    """获取知识库详情"""
    try:
        from app.utils.exceptions import NotFoundException
        try:
            kb = await kb_service_get(db, kb_id)
        except NotFoundException:
            return GetKBOutput(success=False, message="知识库不存在")

        return GetKBOutput(
            success=True,
            kb_info={
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "created_at": str(kb.created_at) if hasattr(kb, "created_at") else None,
            },
            message=f"知识库：{kb.name}",
        )
    except Exception as e:
        logger.error(f"Failed to get knowledge base: {e}")
        return GetKBOutput(success=False, message=f"获取失败：{str(e)}")


async def create_knowledge_base(
    db: AsyncSession,
    user_id: int,
    name: str,
    description: str = "",
) -> CreateKBOutput:
    """创建知识库"""
    try:
        from app.mcp_integration.tools.kb_tools import get_milvus_client
        from app.schemas.knowledge_base import KBCreateRequest
        milvus = get_milvus_client()
        req = KBCreateRequest(name=name, description=description)
        kb = await kb_service_create(db, milvus, req)

        return CreateKBOutput(
            success=True,
            kb_id=str(kb.id),
            kb_name=kb.name,
            message=f"知识库 '{kb.name}' 创建成功",
        )
    except Exception as e:
        logger.error(f"Failed to create knowledge base: {e}")
        return CreateKBOutput(success=False, message=f"创建失败：{str(e)}")


async def delete_knowledge_base(
    db: AsyncSession,
    kb_id: str,
) -> DeleteKBOutput:
    """删除知识库"""
    try:
        from app.mcp_integration.tools.kb_tools import get_milvus_client
        milvus = get_milvus_client()
        await kb_service_delete(db, milvus, kb_id)
        return DeleteKBOutput(success=True, message="知识库已删除")
    except Exception as e:
        logger.error(f"Failed to delete knowledge base: {e}")
        return DeleteKBOutput(success=False, message=f"删除失败：{str(e)}")


async def list_documents(
    db: AsyncSession,
    kb_id: str,
) -> ListDocsOutput:
    """获取文档列表"""
    try:
        docs = await doc_service_list(db, kb_id=kb_id)
        items = [{
            "id": doc.id,
            "name": doc.name,
            "format": getattr(doc, "format", "unknown"),
            "status": getattr(doc, "status", "unknown"),
        } for doc in docs]

        return ListDocsOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个文档",
        )
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        return ListDocsOutput(success=False, message=f"获取失败：{str(e)}")


async def delete_document(
    db: AsyncSession,
    doc_id: str,
) -> DeleteDocOutput:
    """删除文档"""
    try:
        await doc_service_delete(db, doc_id)
        return DeleteDocOutput(success=True, message="文档已删除")
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        return DeleteDocOutput(success=False, message=f"删除失败：{str(e)}")


# ========== LangChain 工具封装 ==========

def get_kb_tools(db: AsyncSession, user_id: int):
    """获取知识库管理工具集"""
    from langchain_core.tools import StructuredTool
    import asyncio

    def _wrapper(func, *args, **kwargs):
        """异步函数包装器"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return [
        StructuredTool.from_function(
            func=lambda search=None: _wrapper(list_knowledge_bases, db, user_id, search),
            name="list_knowledge_bases",
            description="获取知识库列表，可带搜索关键词",
            args_schema=ListKBInput,
        ),
        StructuredTool.from_function(
            func=lambda kb_id: _wrapper(get_knowledge_base, db, kb_id),
            name="get_knowledge_base",
            description="获取知识库详情",
            args_schema=GetKBInput,
        ),
        StructuredTool.from_function(
            func=lambda name, description="": _wrapper(create_knowledge_base, db, user_id, name, description),
            name="create_knowledge_base",
            description="创建新知识库",
            args_schema=CreateKBInput,
        ),
        StructuredTool.from_function(
            func=lambda kb_id: _wrapper(delete_knowledge_base, db, kb_id),
            name="delete_knowledge_base",
            description="删除知识库",
            args_schema=DeleteKBInput,
        ),
        StructuredTool.from_function(
            func=lambda kb_id: _wrapper(list_documents, db, kb_id),
            name="list_documents",
            description="获取知识库中的文档列表",
            args_schema=ListDocsInput,
        ),
        StructuredTool.from_function(
            func=lambda doc_id: _wrapper(delete_document, db, doc_id),
            name="delete_document",
            description="删除文档",
            args_schema=DeleteDocInput,
        ),
    ]
