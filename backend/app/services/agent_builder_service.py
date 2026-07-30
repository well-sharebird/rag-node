"""
Agent Builder Service
根据用户需求自动创建智能体
"""
import json
import logging
import httpx
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentConfig
from app.schemas.chat import AgentCreate, AgentResponse
from app.services.agent_config_service import AgentConfigService
from app.services.model_gateway_service import ModelGatewayService

logger = logging.getLogger("app.services.agent_builder")

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


class AgentBuilderService:
    """Agent 构建服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config_service = AgentConfigService(db)
        self.gateway_service = ModelGatewayService(db)

    async def analyze_requirement(
        self,
        requirement: str,
        user_id: int,
    ) -> dict:
        """
        分析用户需求，生成 Agent 配置

        调用 LLM 分析需求并返回配置 JSON
        """
        # 获取可用的 LLM 模型
        llm = await self.gateway_service.get_best_provider(
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
                "name": "智能助手",
                "description": f"根据需求创建的助手",
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

    async def create_agent_from_requirement(
        self,
        user_id: int,
        tenant_id: Optional[str],
        requirement: str,
        kb_ids: Optional[List[str]] = None,
    ) -> Tuple[AgentConfig, dict]:
        """
        根据需求创建 Agent

        Returns:
            (Agent, analysis_result)
        """
        # 1. 分析需求生成配置
        config = await self.analyze_requirement(requirement, user_id)

        # 2. 提取 system_prompt
        system_prompt = config.pop("system_prompt", "你是一个有帮助的助手。")

        # 3. 创建 Agent
        agent = await self.config_service.create(
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
                kb_ids=kb_ids or config.get("kb_ids", []),
                retrieval_top_k=config.get("retrieval_top_k", 5),
                retrieval_enabled=config.get("retrieval_enabled", False),
                multi_agent_config=config.get("multi_agent_config"),
                is_public=False,
            ),
        )

        return agent, config
