"""
Agent Bootstrap Service
初始化系统预定义的 Agent（如智能体助手）
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import AgentConfig

logger = logging.getLogger(__name__)

# ============================================================
# 预定义 Agent 模板
# ============================================================

META_AGENT_SYSTEM_PROMPT = """你是一个智能体创建和管理助手，拥有自主决策能力。

## 你的能力

你可以通过调用工具来完成以下任务：
1. **创建智能体** - 当用户需要新类型的智能体时，调用 `create_agent` 工具
2. **执行智能体** - 当现有智能体可以完成任务时，调用 `execute_agent` 工具
3. **查询智能体** - 当需要了解现有智能体时，调用 `list_agents` 工具

## 你的工作流程

当用户提出需求时，按以下流程思考和行动：

### 1. 分析用户需求
- 用户想要什么类型的帮助？
- 需要哪些专业能力？
- 是单一任务还是复杂任务？

### 2. 决策：创建新智能体 or 使用现有智能体
- **如果需要新能力** → 调用 `create_agent` 创建新智能体
  - 根据用户需求生成合适的 system_prompt
  - 为智能体起一个描述性的名称
  - 选择合适的技能

- **如果现有智能体可以处理** → 调用 `execute_agent` 执行任务
  - 先调用 `list_agents` 了解现有智能体
  - 选择最匹配的智能体
  - 构造合适的查询

### 3. 创建智能体时的提示词生成
当需要创建智能体时，根据用户描述生成 system_prompt：

**用户说**: "创建一个有产品能力和架构能力的智能体"
**你应该**:
- 创建一个"产品经理助手"智能体，使用产品相关的 system_prompt
- 创建一个"高级架构师"智能体，使用架构相关的 system_prompt

**用户说**: "帮我做一个能分析代码的智能体"
**你应该**:
- 创建一个"代码分析专家"智能体

### 4. 多智能体协作
对于复杂任务，可以：
1. 创建多个专业智能体
2. 依次调用它们完成不同子任务
3. 整合结果返回给用户

## 可用工具

- `create_agent(name, system_prompt, description, agent_type, enabled_skills)` - 创建新智能体
- `execute_agent(agent_id, query)` - 执行现有智能体
- `list_agents(status)` - 查询现有智能体列表

## 回答风格

- 主动思考，自主决策
- 清晰地解释你的决策过程
- 创建智能体时，生成专业、详细的 system_prompt
- 整合多个智能体结果时，提供统一的总结"""


# ============================================================
# Bootstrap 函数
# ============================================================

async def ensure_meta_agent_exists(db: AsyncSession, user_id: int = 1, tenant_id: str = "system") -> str:
    """
    确保"智能体助手"Agent 存在，不存在则创建

    Returns:
        Agent ID
    """
    # 检查是否已存在
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.name == "智能体助手",
            AgentConfig.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"智能体助手已存在：{existing.id}")
        return str(existing.id)

    # 创建智能体助手
    from app.schemas.chat import AgentCreate
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)

    try:
        agent = await service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name="智能体助手",
                description="帮助你创建和管理智能体的自主助手。可以分析你的需求，自主创建合适的智能体，或调用现有智能体完成任务。",
                icon="🤖",
                agent_type="single",
                system_prompt=META_AGENT_SYSTEM_PROMPT,
                enabled_skills=[],
                mcp_servers=[],
                memory_type="conversation",
                memory_ttl_hours=24,
                is_public=True,  # 公开到广场
            )
        )

        logger.info(f"创建智能体助手：{agent.id}")
        return str(agent.id)

    except Exception as e:
        logger.exception(f"创建智能体助手失败：{e}")
        raise


async def ensure_product_manager_agent_exists(db: AsyncSession, user_id: int = 1, tenant_id: str = "system") -> str:
    """
    确保"产品经理助手"Agent 存在（示例预定义 Agent）
    """
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.name == "产品经理助手",
            AgentConfig.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return str(existing.id)

    from app.schemas.chat import AgentCreate
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)

    PRODUCT_MANAGER_PROMPT = """你是一位资深产品经理助手，专注于产品需求分析和产品设计。

## 核心能力
- 产品需求分析：深入理解用户需求，提炼核心痛点，定义产品价值主张
- 需求文档撰写：编写清晰、完整的产品需求文档（PRD）
- 功能设计：设计用户友好的功能流程和交互逻辑
- 优先级评估：使用 MoSCoW、RICE 等方法评估需求优先级

## 工作流程
1. 首先明确业务目标和用户群体
2. 通过 5W1H 方法梳理需求背景
3. 使用用户故事地图梳理功能流程
4. 输出结构化的需求文档
5. 提供可落地的实施建议

## 输出风格
- 逻辑清晰，结构化表达
- 使用图表、流程图辅助说明
- 提供多个方案供选择
- 关注可执行性和落地性"""

    try:
        agent = await service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name="产品经理助手",
                description="专注于产品需求分析、功能设计和 PRD 文档撰写的专业产品经理助手",
                icon="📋",
                agent_type="single",
                system_prompt=PRODUCT_MANAGER_PROMPT,
                enabled_skills=[],
                mcp_servers=[],
                memory_type="conversation",
                memory_ttl_hours=24,
                is_public=True,
            )
        )

        logger.info(f"创建产品经理助手：{agent.id}")
        return str(agent.id)

    except Exception as e:
        logger.exception(f"创建产品经理助手失败：{e}")
        raise


async def ensure_architect_agent_exists(db: AsyncSession, user_id: int = 1, tenant_id: str = "system") -> str:
    """
    确保"高级架构师"Agent 存在（示例预定义 Agent）
    """
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.name == "高级架构师",
            AgentConfig.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return str(existing.id)

    from app.schemas.chat import AgentCreate
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)

    ARCHITECT_PROMPT = """你是一位资深技术架构师，专注于系统架构设计和技术选型。

## 核心能力
- 系统架构设计：设计高可用、可扩展的系统架构
- 技术选型：评估技术方案，提供选型建议
- 代码审查：审查代码结构，提出改进意见
- 性能优化：设计高性能、低延迟的系统

## 工作流程
1. 分析业务需求和技术约束
2. 设计系统架构和模块划分
3. 评估技术选型方案
4. 输出架构设计文档
5. 提供实施路线图

## 输出风格
- 技术深度强，考虑周全
- 注重可维护性和扩展性
- 提供具体的实现建议
- 使用架构图和流程图说明"""

    try:
        agent = await service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name="高级架构师",
                description="专注于系统架构设计、技术选型和代码审查的资深架构师",
                icon="🏗️",
                agent_type="single",
                system_prompt=ARCHITECT_PROMPT,
                enabled_skills=[],
                mcp_servers=[],
                memory_type="conversation",
                memory_ttl_hours=24,
                is_public=True,
            )
        )

        logger.info(f"创建高级架构师：{agent.id}")
        return str(agent.id)

    except Exception as e:
        logger.exception(f"创建高级架构师失败：{e}")
        raise


# ============================================================
# 初始化入口
# ============================================================

async def ensure_ai_assistant_agent_exists(db: AsyncSession, user_id: int = 1, tenant_id: str = "system") -> str:
    """
    确保"AI 助手"Agent 存在（用于 QAChatView 的通用问答）

    Returns:
        Agent ID
    """
    result = await db.execute(
        select(AgentConfig).where(
            AgentConfig.name == "AI 助手",
            AgentConfig.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"AI 助手已存在：{existing.id}")
        return str(existing.id)

    from app.schemas.chat import AgentCreate
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)

    AI_ASSISTANT_PROMPT = """你是一个专业的 AI 助手，基于检索到的知识库内容回答用户问题。

## 回答规则

1. **优先使用检索内容** - 以检索到的知识库内容作为回答依据
2. **诚实告知** - 如果知识库中没有相关信息，明确告知用户
3. **准确简洁** - 回答要准确、简洁、有条理
4. **主动澄清** - 如果问题模糊，主动询问用户以澄清需求
5. **专业详细** - 对于专业问题，提供详细的解释和必要的背景信息

## 输出格式

- 使用 Markdown 格式组织回答
- 对于复杂问题，分点列出
- 引用知识库内容时，注明来源"""

    try:
        agent = await service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name="AI 助手",
                description="通用 AI 助手，支持 RAG 检索增强生成，可回答用户问题",
                icon="🤖",
                agent_type="single",
                system_prompt=AI_ASSISTANT_PROMPT,
                enabled_skills=[],
                mcp_servers=[],
                memory_type="conversation",
                memory_ttl_hours=24,
                is_public=True,
            )
        )

        logger.info(f"创建 AI 助手：{agent.id}")
        return str(agent.id)

    except Exception as e:
        logger.exception(f"创建 AI 助手失败：{e}")
        raise


async def init_system_agents(db: AsyncSession) -> dict[str, str]:
    """
    初始化系统预定义 Agent

    Returns:
        {agent_name: agent_id} 映射
    """
    agent_ids = {}

    try:
        # 创建 AI 助手（用于 QAChatView）
        ai_id = await ensure_ai_assistant_agent_exists(db)
        agent_ids["ai_assistant"] = ai_id

        # 创建智能体助手（必须）
        meta_id = await ensure_meta_agent_exists(db)
        agent_ids["meta_agent"] = meta_id

        # 创建示例 Agent（可选）
        try:
            pm_id = await ensure_product_manager_agent_exists(db)
            agent_ids["product_manager"] = pm_id
        except Exception as e:
            logger.warning(f"创建产品经理助手失败：{e}")

        try:
            arch_id = await ensure_architect_agent_exists(db)
            agent_ids["architect"] = arch_id
        except Exception as e:
            logger.warning(f"创建高级架构师失败：{e}")

    except Exception as e:
        logger.exception(f"初始化系统 Agent 失败：{e}")
        raise

    return agent_ids
