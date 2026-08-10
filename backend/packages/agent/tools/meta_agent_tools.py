"""
Meta Agent 工具集
用于主智能体自主创建和管理其他智能体
"""
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ============================================================
# 工具定义 - 用于 Meta Agent 自主调用
# ============================================================

def create_create_agent_tool(db: AsyncSession, user_id: int, tenant_id: str):
    """
    创建 create_agent 工具
    允许 Meta Agent 动态创建新的智能体
    """
    from langchain_core.tools import tool
    from packages.agent.services.agent_config_service import AgentConfigService

    @tool
    async def create_agent(
        name: str = Field(..., description="智能体名称，如'产品经理助手'、'高级架构师'"),
        system_prompt: str = Field(..., description="智能体的系统提示词，定义其角色和能力"),
        description: str = Field("", description="智能体描述"),
        agent_type: str = Field("single", description="智能体类型：single 或 multi"),
        enabled_skills: list[str] = Field(default_factory=list, description="启用的技能列表"),
    ) -> str:
        """
        Create a new agent with specified capabilities.

        Use this tool when:
        - User asks you to create a new agent
        - You need a specialized agent for a specific task
        - No existing agent matches the user's needs

        Args:
            name: Clear, descriptive name for the agent (e.g., "产品经理助手", "高级架构师")
            system_prompt: Detailed system prompt defining the agent's role, expertise, and behavior
            description: Brief description of what the agent does
            agent_type: "single" for simple agents, "multi" for multi-agent orchestration
            enabled_skills: List of skill IDs the agent should have access to

        Returns:
            Success or error message
        """
        try:
            from packages.agent.schemas.chat import AgentCreate
            from packages.core.database import async_session_factory

            # 创建新的独立 session，避免与当前 Agent 执行的 session 冲突
            async with async_session_factory() as new_session:
                service = AgentConfigService(new_session)

                # 创建智能体
                agent = await service.create(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    data=AgentCreate(
                        name=name,
                        description=description,
                        icon="🤖",
                        agent_type=agent_type,
                        system_prompt=system_prompt,
                        enabled_skills=enabled_skills,
                        mcp_servers=[],
                        memory_type="conversation",
                        memory_ttl_hours=24,
                        is_public=False,
                    )
                )

                logger.info(f"[MetaAgent] Created agent: {name} (ID: {agent.id})")

                return f"Successfully created agent '{name}' (ID: {agent.id}). The agent is now available for use."

        except Exception as e:
            logger.exception(f"[MetaAgent] Failed to create agent: {e}")
            return f"Failed to create agent: {str(e)}"

    return create_agent


def create_execute_agent_tool(db: AsyncSession, user_id: int, kb_ids: Optional[list[str]] = None, top_k: int = 5, enable_rerank: bool = False, model_name: Optional[str] = None):
    """
    创建 execute_agent 工具
    允许 Meta Agent 调用现有智能体完成任务
    """
    from langchain_core.tools import tool
    from packages.agent.services.harness_agent_service import create_harness_agent_service

    @tool
    async def execute_agent(
        agent_id: str = Field(..., description="智能体 ID"),
        query: str = Field(..., description="要执行的任务或问题"),
    ) -> str:
        """
        Execute an existing agent to complete a task.

        Use this tool when:
        - You need to use an existing agent's capabilities
        - A subtask is better handled by a specialized agent
        - User requests something an existing agent can handle

        Args:
            agent_id: ID of the agent to execute
            query: The task or question to ask the agent

        Returns:
            The agent's response as a string
        """
        try:
            from packages.agent.services.harness_agent_service import create_harness_agent_service
            from packages.model_gateway.services.model_gateway_service import ModelGatewayService
            from packages.agent.services.skill_registry import RegistryService as SkillRegistryService

            model_gateway = ModelGatewayService(db)
            skill_registry = SkillRegistryService(db)
            harness_service = await create_harness_agent_service(db, model_gateway, skill_registry)

            result = await harness_service.execute(
                agent_id=agent_id,
                query=query,
                user_id=user_id,
                tenant_id="default",
                kb_ids=kb_ids,
                top_k=top_k,
                enable_rerank=enable_rerank,
                model_name=model_name,
            )

            logger.info(f"[MetaAgent] Executed agent {agent_id}, response length: {len(result.response)}")

            return result.response

        except Exception as e:
            logger.exception(f"[MetaAgent] Failed to execute agent: {e}")
            return f"Error executing agent: {str(e)}"

    return execute_agent


def create_list_agents_tool(db: AsyncSession, user_id: int):
    """
    创建 list_agents 工具
    允许 Meta Agent 查询现有智能体
    """
    from langchain_core.tools import tool
    from packages.agent.services.agent_config_service import AgentConfigService

    @tool
    async def list_agents(
        status: Optional[str] = Field(None, description="过滤状态：draft, active, archived, disabled"),
    ) -> list[dict]:
        """
        List available agents that can be used.

        Use this tool when:
        - You need to know what agents are available
        - User asks about existing agents
        - You want to reuse an existing agent instead of creating a new one

        Returns:
            List of agents with id, name, description, agent_type
        """
        try:
            service = AgentConfigService(db)
            agents, total = await service.list(
                user_id=user_id,
                status=status,
                skip=0,
                limit=50
            )

            return [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "description": a.description,
                    "agent_type": a.agent_type,
                    "status": a.status
                }
                for a in agents
            ]

        except Exception as e:
            logger.exception(f"[MetaAgent] Failed to list agents: {e}")
            return []

    return list_agents


# ============================================================
# 专业智能体提示词模板
# ============================================================

AGENT_PROMPT_TEMPLATES = {
    "product_manager": """你是一个专业的产品经理助手，具备以下能力：
- 产品需求分析和文档撰写
- 用户故事和功能规格定义
- 竞品分析和市场调研
- 产品路线图规划

你的职责：
1. 理解用户需求，提取关键功能点
2. 撰写清晰的产品需求文档 (PRD)
3. 定义用户故事和验收标准
4. 提供产品设计和迭代建议

回答风格：
- 结构化、逻辑清晰
- 注重用户价值和商业目标
- 提供可执行的建议""",

    "architect": """你是一个高级技术架构师，具备以下能力：
- 系统架构设计和评审
- 技术选型和方案对比
- 代码质量和最佳实践审查
- 性能优化和可扩展性设计

你的职责：
1. 分析技术需求，设计系统架构
2. 评估技术方案，提供选型建议
3. 审查代码结构，提出改进意见
4. 设计高性能、可扩展的系统

回答风格：
- 技术深度强，考虑周全
- 注重可维护性和扩展性
- 提供具体的实现建议""",

    "developer": """你是一个资深软件工程师，具备以下能力：
- 代码编写和审查
- Bug 排查和问题解决
- 技术文档撰写
- 开发最佳实践

你的职责：
1. 编写高质量代码
2. 代码审查和技术指导
3. 解决技术难题
4. 撰写技术文档

回答风格：
- 代码示例清晰
- 解释详细易懂
- 注重实践性""",

    "researcher": """你是一个研究分析专家，具备以下能力：
- 信息搜集和整理
- 数据分析和洞察
- 研究报告撰写
- 趋势分析和预测

你的职责：
1. 搜集和整理相关信息
2. 分析数据，提取关键洞察
3. 撰写结构化的研究报告
4. 提供趋势分析和建议

回答风格：
- 数据驱动
- 引用可靠来源
- 结论清晰有说服力""",
}


def get_agent_prompt_template(role: str) -> str:
    """
    根据角色获取预定义的系统提示词模板

    Args:
        role: 角色类型，如 "product_manager", "architect" 等

    Returns:
        系统提示词模板
    """
    return AGENT_PROMPT_TEMPLATES.get(role, """你是一个专业的 AI 助手，致力于帮助用户完成任务。
你有丰富的知识和分析能力，能够提供有价值的建议和支持。
请保持专业、友好的态度，提供清晰、结构化的回答。""")
