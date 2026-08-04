"""
提示词工程管理 Skill
提供提示词模板查询、创建、测试等工具
"""
import logging
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.models.prompt_template import PromptTemplate, PromptVersion, PromptTestCase

logger = logging.getLogger("app.skills.prompt")

# ========== 系统提示词 ==========
PROMPT_TOOL_PROMPT = """你是提示词工程专家，可以帮用户执行以下操作：

## 可用工具
1. **list_prompts** - 获取提示词模板列表
2. **get_prompt** - 获取提示词详情和版本
3. **create_prompt** - 创建新提示词模板
4. **list_test_cases** - 获取测试用例列表
5. **run_test** - 运行提示词测试

## 使用场景
- 用户问"有哪些提示词模板" → 调用 list_prompts
- 用户问"XX 提示词怎么写" → 调用 get_prompt
- 用户要优化提示词 → 调用 run_test 测试效果

## 输出规范
- 列表类：展示名称、版本数、状态
- 详情类：展示完整提示词内容和版本历史
- 测试类：展示输入输出对比和评分
"""


# ========== 输入输出 Schema ==========

class ListPromptsInput(BaseModel):
    """获取提示词列表"""
    search: Optional[str] = Field(None, description="搜索关键词")
    limit: int = Field(20, description="返回数量限制")


class ListPromptsOutput(BaseModel):
    """提示词列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class GetPromptInput(BaseModel):
    """获取提示词详情"""
    prompt_name: str = Field(..., description="提示词模板名称")


class GetPromptOutput(BaseModel):
    """提示词详情输出"""
    success: bool
    prompt_info: Optional[dict] = None
    versions: List[dict] = []
    message: str = ""


class CreatePromptInput(BaseModel):
    """创建提示词"""
    name: str = Field(..., description="提示词名称", max_length=100)
    content: str = Field(..., description="提示词内容")
    description: str = Field("", description="描述")


class CreatePromptOutput(BaseModel):
    """创建提示词输出"""
    success: bool
    prompt_id: Optional[int] = None
    message: str = ""


class ListTestCasesInput(BaseModel):
    """获取测试用例列表"""
    prompt_name: str = Field(..., description="提示词名称")
    limit: int = Field(20, description="返回数量限制")


class ListTestCasesOutput(BaseModel):
    """测试用例列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class RunTestInput(BaseModel):
    """运行测试"""
    prompt_name: str = Field(..., description="提示词名称")
    test_input: str = Field(..., description="测试输入")


class RunTestOutput(BaseModel):
    """测试输出"""
    success: bool
    output: Optional[str] = None
    latency_ms: Optional[float] = None
    message: str = ""


# ========== 工具函数 ==========

async def list_prompts_tool(
    db: AsyncSession,
    search: Optional[str] = None,
    limit: int = 20,
) -> ListPromptsOutput:
    """获取提示词列表"""
    try:
        query = select(PromptTemplate).order_by(PromptTemplate.created_at.desc()).limit(limit)

        if search:
            query = query.where(PromptTemplate.name.ilike(f"%{search}%"))

        result = await db.execute(query)
        templates = list(result.scalars().all())

        items = []
        for t in templates:
            # 获取版本数
            version_count = await db.execute(
                select(PromptVersion).where(PromptVersion.prompt_name == t.name)
            )
            version_count = len(list(version_count.scalars().all()))

            items.append({
                "name": t.name,
                "description": t.description,
                "current_version": t.current_version,
                "version_count": version_count,
                "is_released": t.is_released,
                "created_at": str(t.created_at) if hasattr(t, "created_at") else None,
            })

        return ListPromptsOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个提示词模板",
        )
    except Exception as e:
        logger.error(f"Failed to list prompts: {e}")
        return ListPromptsOutput(success=False, message=f"获取失败：{str(e)}")


async def get_prompt_tool(
    db: AsyncSession,
    prompt_name: str,
) -> GetPromptOutput:
    """获取提示词详情"""
    try:
        # 获取模板
        result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == prompt_name)
        )
        template = result.scalar_one_or_none()

        if not template:
            return GetPromptOutput(success=False, message="提示词模板不存在")

        # 获取版本列表
        result = await db.execute(
            select(PromptVersion)
            .where(PromptVersion.prompt_name == prompt_name)
            .order_by(PromptVersion.created_at.desc())
        )
        versions = list(result.scalars().all())

        version_list = []
        for v in versions:
            version_list.append({
                "version": v.version,
                "content": v.content[:200] + "..." if len(v.content) > 200 else v.content,
                "is_released": v.is_released,
                "released_at": str(v.released_at) if v.released_at else None,
                "created_at": str(v.created_at) if hasattr(v, "created_at") else None,
            })

        return GetPromptOutput(
            success=True,
            prompt_info={
                "name": template.name,
                "description": template.description,
                "current_version": template.current_version,
                "current_content": template.current_content,
                "is_released": template.is_released,
            },
            versions=version_list,
            message=f"提示词：{template.name} (当前版本：{template.current_version})",
        )
    except Exception as e:
        logger.error(f"Failed to get prompt: {e}")
        return GetPromptOutput(success=False, message=f"获取失败：{str(e)}")


async def create_prompt_tool(
    db: AsyncSession,
    name: str,
    content: str,
    description: str = "",
) -> CreatePromptOutput:
    """创建提示词模板"""
    try:
        # 检查是否已存在
        exists = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == name)
        )
        if exists.scalar_one_or_none():
            return CreatePromptOutput(
                success=False,
                message=f"提示词模板 '{name}' 已存在",
            )

        # 创建模板
        template = PromptTemplate(
            name=name,
            description=description,
            current_version="v1.0",
            current_content=content,
            is_released=False,
        )
        db.add(template)

        # 创建第一个版本
        version = PromptVersion(
            prompt_name=name,
            version="v1.0",
            content=content,
            is_released=False,
        )
        db.add(version)

        await db.commit()

        return CreatePromptOutput(
            success=True,
            prompt_id=template.id,
            message=f"提示词模板 '{name}' 创建成功",
        )
    except Exception as e:
        logger.error(f"Failed to create prompt: {e}")
        await db.rollback()
        return CreatePromptOutput(success=False, message=f"创建失败：{str(e)}")


async def list_test_cases_tool(
    db: AsyncSession,
    prompt_name: str,
    limit: int = 20,
) -> ListTestCasesOutput:
    """获取测试用例列表"""
    try:
        result = await db.execute(
            select(PromptTestCase)
            .where(PromptTestCase.prompt_name == prompt_name)
            .order_by(PromptTestCase.created_at.desc())
            .limit(limit)
        )
        test_cases = list(result.scalars().all())

        items = []
        for tc in test_cases:
            items.append({
                "id": tc.id,
                "name": tc.name,
                "input": tc.input[:100] + "..." if len(tc.input) > 100 else tc.input,
                "expected_output": tc.expected_output[:100] + "..." if tc.expected_output and len(tc.expected_output) > 100 else tc.expected_output,
                "category": tc.category,
            })

        return ListTestCasesOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个测试用例",
        )
    except Exception as e:
        logger.error(f"Failed to list test cases: {e}")
        return ListTestCasesOutput(success=False, message=f"获取失败：{str(e)}")


async def run_test_tool(
    db: AsyncSession,
    prompt_name: str,
    test_input: str,
) -> RunTestOutput:
    """运行提示词测试"""
    import time
    import httpx
    from app.services.model_config_service import resolve_llm_config

    try:
        # 获取提示词
        result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == prompt_name)
        )
        template = result.scalar_one_or_none()

        if not template:
            return RunTestOutput(success=False, message="提示词模板不存在")

        # 获取 LLM 配置
        llm_config = await resolve_llm_config(db)
        if not llm_config:
            return RunTestOutput(success=False, message="未配置 LLM 模型")

        # 构造完整提示词
        full_prompt = template.current_content.replace("{input}", test_input)

        # 调用 LLM
        start_time = time.time()

        # 获取 provider
        provider_result = await db.execute(
            select(ModelProvider).where(ModelProvider.code == llm_config.provider)
        )
        provider = provider_result.scalar_one_or_none()

        if not provider:
            return RunTestOutput(success=False, message="未找到模型供应商")

        base_url = provider.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            api_url = f"{base_url}/v1/chat/completions"
        else:
            api_url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                api_url,
                json={
                    "model": llm_config.model_id,
                    "messages": [
                        {"role": "system", "content": "你是一个有帮助的助手"},
                        {"role": "user", "content": full_prompt},
                    ],
                    "max_tokens": 500,
                },
                headers=headers,
            )

            if response.status_code != 200:
                return RunTestOutput(
                    success=False,
                    message=f"LLM 调用失败：{response.status_code}",
                )

            data = response.json()
            output = data["choices"][0]["message"].get("content", "")
            latency_ms = (time.time() - start_time) * 1000

            return RunTestOutput(
                success=True,
                output=output,
                latency_ms=latency_ms,
                message=f"测试完成，耗时 {latency_ms:.0f}ms",
            )

    except Exception as e:
        logger.error(f"Failed to run test: {e}")
        return RunTestOutput(success=False, message=f"测试失败：{str(e)}")


# ========== LangChain 工具封装 ==========

def get_prompt_tools(db: AsyncSession) -> list:
    """获取提示词管理工具集"""
    from langchain_core.tools import StructuredTool
    import asyncio

    def _wrapper(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return [
        StructuredTool.from_function(
            func=lambda search=None, limit=20: _wrapper(
                list_prompts_tool, db, search, limit
            ),
            name="list_prompts",
            description="获取提示词模板列表",
            args_schema=ListPromptsInput,
        ),
        StructuredTool.from_function(
            func=lambda prompt_name: _wrapper(
                get_prompt_tool, db, prompt_name
            ),
            name="get_prompt",
            description="获取提示词详情和版本历史",
            args_schema=GetPromptInput,
        ),
        StructuredTool.from_function(
            func=lambda name, content, description="": _wrapper(
                create_prompt_tool, db, name, content, description
            ),
            name="create_prompt",
            description="创建新提示词模板",
            args_schema=CreatePromptInput,
        ),
        StructuredTool.from_function(
            func=lambda prompt_name, limit=20: _wrapper(
                list_test_cases_tool, db, prompt_name, limit
            ),
            name="list_test_cases",
            description="获取提示词的测试用例列表",
            args_schema=ListTestCasesInput,
        ),
        StructuredTool.from_function(
            func=lambda prompt_name, test_input: _wrapper(
                run_test_tool, db, prompt_name, test_input
            ),
            name="run_test",
            description="运行提示词测试",
            args_schema=RunTestInput,
        ),
    ]


# 需要导入 ModelProvider
from app.models.model_gateway import ModelProvider
