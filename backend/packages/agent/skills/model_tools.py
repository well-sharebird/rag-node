"""
模型管理 Skill
提供模型查询、测试、配置管理等工具
"""
import logging
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from packages.model_gateway.models.model_config import ModelConfig
from packages.model_gateway.models.model_gateway import ModelProvider
from packages.model_gateway.services.model_service import get_model, list_models
from packages.model_gateway.services.model_config_service import (
    resolve_llm_config,
    resolve_embedding_config,
    resolve_rerank_config,
)

logger = logging.getLogger("app.skills.model")

# ========== 系统提示词 ==========
MODEL_TOOL_PROMPT = """你是模型管理专家，可以帮用户执行以下操作：

## 可用工具
1. **list_models** - 获取模型配置列表
2. **list_providers** - 获取模型供应商列表
3. **get_default_model** - 获取默认模型配置
4. **test_model** - 测试模型连接

## 使用场景
- 用户问"有哪些模型" → 调用 list_models
- 用户问"当前用的什么模型" → 调用 get_default_model
- 用户问"模型连接正常吗" → 调用 test_model

## 输出规范
- 列表类：简洁展示名称、类型、状态
- 配置类：展示关键参数（model_id、provider、状态）
- 测试类：返回成功/失败和延迟
"""


# ========== 输入输出 Schema ==========

class ListModelsInput(BaseModel):
    """获取模型列表"""
    model_type: Optional[str] = Field(None, description="模型类型：llm, embedding, rerank")
    enabled_only: bool = Field(True, description="是否只看启用的模型")


class ListModelsOutput(BaseModel):
    """模型列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class ListProvidersInput(BaseModel):
    """获取供应商列表"""
    provider_type: Optional[str] = Field(None, description="供应商类型")


class ListProvidersOutput(BaseModel):
    """供应商列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class GetDefaultModelInput(BaseModel):
    """获取默认模型"""
    model_type: str = Field(..., description="模型类型：llm, embedding, rerank")


class GetDefaultModelOutput(BaseModel):
    """默认模型输出"""
    success: bool
    model_info: Optional[dict] = None
    message: str = ""


class TestModelInput(BaseModel):
    """测试模型连接"""
    model_id: int = Field(..., description="模型配置 ID")


class TestModelOutput(BaseModel):
    """测试模型输出"""
    success: bool
    latency_ms: Optional[float] = None
    message: str = ""


# ========== 工具函数 ==========

async def list_models_tool(
    db: AsyncSession,
    model_type: Optional[str] = None,
    enabled_only: bool = True,
) -> ListModelsOutput:
    """获取模型列表"""
    try:
        models = await list_models(db, model_type=model_type, enabled_only=enabled_only)

        items = []
        for m in models:
            items.append({
                "id": m.id,
                "name": m.name,
                "model_id": m.model_id,
                "model_type": m.model_type,
                "provider": m.provider,
                "is_enabled": m.is_enabled,
                "is_default": m.is_default,
                "status": m.status,
            })

        return ListModelsOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个模型",
        )
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        return ListModelsOutput(success=False, message=f"获取失败：{str(e)}")


async def list_providers_tool(
    db: AsyncSession,
    provider_type: Optional[str] = None,
) -> ListProvidersOutput:
    """获取供应商列表"""
    try:
        query = select(ModelProvider)
        if provider_type:
            query = query.where(ModelProvider.provider_type == provider_type)

        result = await db.execute(query)
        providers = list(result.scalars().all())

        items = []
        for p in providers:
            items.append({
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "is_enabled": p.is_enabled,
                "status": p.status,
            })

        return ListProvidersOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个供应商",
        )
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        return ListProvidersOutput(success=False, message=f"获取失败：{str(e)}")


async def get_default_model_tool(
    db: AsyncSession,
    model_type: str,
) -> GetDefaultModelOutput:
    """获取默认模型"""
    try:
        if model_type == "llm":
            config = await resolve_llm_config(db)
        elif model_type == "embedding":
            config = await resolve_embedding_config(db)
        elif model_type == "rerank":
            config = await resolve_rerank_config(db)
        else:
            return GetDefaultModelOutput(success=False, message=f"未知模型类型：{model_type}")

        if not config:
            return GetDefaultModelOutput(
                success=False,
                message=f"未配置默认{model_type}模型",
            )

        return GetDefaultModelOutput(
            success=True,
            model_info={
                "id": config.id,
                "name": config.name,
                "model_id": config.model_id,
                "provider": config.provider,
                "is_enabled": config.is_enabled,
            },
            message=f"默认{model_type}模型：{config.name}",
        )
    except Exception as e:
        logger.error(f"Failed to get default model: {e}")
        return GetDefaultModelOutput(success=False, message=f"获取失败：{str(e)}")


async def test_model_tool(
    db: AsyncSession,
    model_id: int,
) -> TestModelOutput:
    """测试模型连接"""
    try:
        from packages.model_gateway.services.model_service import test_model_connection

        result = await test_model_connection(db, model_id)

        return TestModelOutput(
            success=result.get("success", False),
            latency_ms=result.get("latency_ms"),
            message=result.get("message", "测试完成"),
        )
    except Exception as e:
        logger.error(f"Failed to test model: {e}")
        return TestModelOutput(success=False, message=f"测试失败：{str(e)}")


# ========== LangChain 工具封装 ==========

def get_model_tools(db: AsyncSession) -> list:
    """获取模型管理工具集"""
    from langchain_core.tools import StructuredTool
    import asyncio

    def _wrapper(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return [
        StructuredTool.from_function(
            func=lambda model_type=None, enabled_only=True: _wrapper(
                list_models_tool, db, model_type, enabled_only
            ),
            name="list_models",
            description="获取模型配置列表，可按类型过滤",
            args_schema=ListModelsInput,
        ),
        StructuredTool.from_function(
            func=lambda provider_type=None: _wrapper(
                list_providers_tool, db, provider_type
            ),
            name="list_providers",
            description="获取模型供应商列表",
            args_schema=ListProvidersInput,
        ),
        StructuredTool.from_function(
            func=lambda model_type: _wrapper(
                get_default_model_tool, db, model_type
            ),
            name="get_default_model",
            description="获取默认模型配置 (llm/embedding/rerank)",
            args_schema=GetDefaultModelInput,
        ),
        StructuredTool.from_function(
            func=lambda model_id: _wrapper(
                test_model_tool, db, model_id
            ),
            name="test_model",
            description="测试模型连接状态",
            args_schema=TestModelInput,
        ),
    ]
