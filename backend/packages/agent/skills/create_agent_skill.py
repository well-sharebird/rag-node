"""
创建智能体 Skill
可被其他 Agent 调用以创建新的智能体
"""
import json
import logging
import httpx
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from packages.agent.models.agent import AgentConfig
from packages.agent.schemas.chat import AgentCreate
from packages.agent.services.agent_config_service import AgentConfigService
from packages.model_gateway.services.model_gateway_service import ModelGatewayService

logger = logging.getLogger("app.skills.create_agent")

# Agent Builder 的系统提示词
AGENT_BUILDER_PROMPT = """你是一个智能体配置专家。根据用户的需求描述，分析并生成合适的智能体配置。

## 任务
分析用户需求，生成以下配置 JSON：

1. **name**: 简洁明确的智能体名称（20 字以内）
2. **description**: 功能描述（50 字以内）
3. **system_prompt**: 详细的系统提示词，包括角色定位、核心职责、工作流程、输出规范
4. **agent_type**: "single" 或 "multi"（复杂任务需要多智能体协作时选 multi）
5. **memory_type**:
   - "conversation": 仅需对话历史（客服、问答类）
   - "vector": 需要长期记忆和知识沉淀（学习助手、个人助理）
   - "hybrid": 两者都需要
6. **retrieval_enabled**: 是否需要检索外部知识库
7. **enabled_skills**: 需要的技能列表，可选值：["web_search", "code_interpreter", "file_processor", "data_analysis"]
8. **multi_agent_config**: 当 agent_type="multi" 时配置

## 输出格式
严格输出 JSON 格式，不要任何额外说明：
{
  "name": "智能体名称",
  "description": "描述",
  "system_prompt": "详细提示词",
  "agent_type": "single",
  "memory_type": "conversation",
  "retrieval_enabled": false,
  "enabled_skills": [],
  "multi_agent_config": null
}

## 示例
用户需求："我需要一个智能体帮我写技术文档"
输出：
{
  "name": "技术文档写作助手",
  "description": "专业的技术文档写作助手，支持 API 文档、用户手册等",
  "system_prompt": "你是一位经验丰富的技术文档工程师，擅长将复杂的技术概念转化为清晰易懂的文档。你熟悉 Markdown、OpenAPI 规范，了解技术写作最佳实践。",
  "agent_type": "single",
  "memory_type": "conversation",
  "retrieval_enabled": true,
  "enabled_skills": ["file_processor"],
  "multi_agent_config": null
}
"""


class CreateAgentInput(BaseModel):
    """创建 Agent Skill 的输入"""
    requirement: str = Field(..., description="用户需求描述，例如'我需要一个帮我写周报的助手'")
    kb_ids: Optional[List[str]] = Field(None, description="可选：关联的知识库 ID 列表")


class CreateAgentOutput(BaseModel):
    """创建 Agent Skill 的输出"""
    success: bool
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    message: str


async def analyze_requirement(
    db: AsyncSession,
    requirement: str,
    user_id: int,
) -> dict:
    """
    分析用户需求，生成 Agent 配置

    调用 LLM 分析需求并返回配置 JSON
    """
    gateway = ModelGatewayService(db)

    # 获取可用的 LLM 模型
    llm = await gateway.get_best_provider(
        model_type="llm",
        user_id=user_id,
    )

    if not llm:
        raise ValueError("No available LLM provider")

    # 构造提示词
    prompt = f"""{AGENT_BUILDER_PROMPT}

用户需求：{requirement}

请分析并生成配置 JSON："""

    # 调用 LLM API
    try:
        base_url = llm.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            api_url = f"{base_url}/v1/chat/completions"
        else:
            api_url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if llm.api_key:
            headers["Authorization"] = f"Bearer {llm.api_key}"

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                api_url,
                json={
                    "model": llm.code,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text[:200]}")
                raise ValueError(f"LLM API error: {response.status_code}")

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # 解析 LLM 返回的 JSON
            # 尝试提取 JSON（LLM 可能返回 markdown 包裹）
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]

            config = json.loads(content)
            return config

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {e}, raw: {content}")
        # 返回默认配置
        return {
            "name": f"智能助手",
            "description": f"根据需求创建的助手：{requirement[:50]}...",
            "system_prompt": "你是一个有帮助的助手。",
            "agent_type": "single",
            "memory_type": "conversation",
            "retrieval_enabled": False,
            "enabled_skills": [],
            "multi_agent_config": None,
        }
    except Exception as e:
        logger.error(f"Error analyzing requirement: {e}")
        raise


async def create_agent_skill(
    db: AsyncSession,
    user_id: int,
    tenant_id: Optional[str],
    input_data: CreateAgentInput,
) -> CreateAgentOutput:
    """
    创建智能体 Skill

    这是一个可被其他 Agent 调用的工具函数
    """
    try:
        # 1. 分析需求生成配置
        config = await analyze_requirement(db, input_data.requirement, user_id)

        # 2. 提取 system_prompt
        system_prompt = config.pop("system_prompt", "你是一个有帮助的助手。")

        # 3. 创建 Agent
        config_service = AgentConfigService(db)
        agent = await config_service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name=config.get("name", f"智能助手-{user_id}"),
                description=config.get("description", ""),
                icon=config.get("icon"),
                agent_type=config.get("agent_type", "single"),
                system_prompt=system_prompt,
                enabled_skills=config.get("enabled_skills", []),
                mcp_servers=config.get("mcp_servers", []),
                memory_type=config.get("memory_type", "conversation"),
                memory_ttl_hours=config.get("memory_ttl_hours", 24),
                max_memory_turns=config.get("max_memory_turns", 50),
                kb_ids=input_data.kb_ids or config.get("kb_ids", []),
                retrieval_top_k=config.get("retrieval_top_k", 5),
                retrieval_enabled=config.get("retrieval_enabled", False),
                multi_agent_config=config.get("multi_agent_config"),
                is_public=False,
            ),
        )

        return CreateAgentOutput(
            success=True,
            agent_id=str(agent.id),
            agent_name=agent.name,
            message=f"智能体'{agent.name}'创建成功，可以开始使用了",
        )

    except Exception as e:
        logger.exception("Failed to create agent from requirement")
        return CreateAgentOutput(
            success=False,
            message=f"创建失败：{str(e)}",
        )


def get_create_agent_tool(db: AsyncSession, user_id: int, tenant_id: Optional[str]):
    """
    获取创建 Agent 的 Tool 实例（LangChain 格式）

    用于绑定到 Agent 的 LLM 上
    """
    import asyncio
    from langchain_core.tools import StructuredTool

    def _create_agent_wrapper(requirement: str, kb_ids: Optional[List[str]] = None) -> dict:
        """创建智能体的包装函数"""
        loop = asyncio.get_event_loop()
        input_data = CreateAgentInput(requirement=requirement, kb_ids=kb_ids)
        result = loop.run_until_complete(create_agent_skill(db, user_id, tenant_id, input_data))
        return result.model_dump()

    return StructuredTool.from_function(
        func=_create_agent_wrapper,
        name="create_agent",
        description="根据用户需求创建新的智能体。当用户想要创建新助手、新代理、新机器人时调用。",
        args_schema=CreateAgentInput,
    )
