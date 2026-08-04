"""
智能体管理 Skill
提供智能体查询、创建、配置管理等工具
"""
import logging
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.models.agent import AgentConfig
from app.services.agent_config_service import AgentConfigService
from app.schemas.chat import AgentCreate

logger = logging.getLogger("app.skills.agent")

# ========== 系统提示词 ==========
AGENT_TOOL_PROMPT = """你是智能体管理专家，可以帮用户执行以下操作：

## 可用工具
1. **list_agents** - 获取智能体列表
2. **get_agent** - 获取智能体详情
3. **create_agent** - 创建新智能体
4. **update_agent** - 更新智能体配置
5. **delete_agent** - 删除智能体
6. **get_agent_plaza** - 获取智能体广场（公共智能体）

## 使用场景
- 用户问"有哪些智能体" → 调用 list_agents
- 用户问"XX 智能体怎么配置的" → 调用 get_agent
- 用户要创建新智能体 → 调用 create_agent
- 用户想逛智能体广场 → 调用 get_agent_plaza

## 输出规范
- 列表类：展示名称、类型、状态
- 详情类：展示完整配置（system_prompt、技能、记忆配置等）
- 操作类：返回成功/失败和影响
"""


# ========== 输入输出 Schema ==========

class ListAgentsInput(BaseModel):
    """获取智能体列表"""
    agent_type: Optional[str] = Field(None, description="智能体类型：single, multi")
    include_public: bool = Field(True, description="是否包含公共智能体")
    limit: int = Field(20, description="返回数量限制")


class ListAgentsOutput(BaseModel):
    """智能体列表输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


class GetAgentInput(BaseModel):
    """获取智能体详情"""
    agent_id: str = Field(..., description="智能体 ID")


class GetAgentOutput(BaseModel):
    """智能体详情输出"""
    success: bool
    agent_info: Optional[dict] = None
    message: str = ""


class CreateAgentInput(BaseModel):
    """创建智能体"""
    name: str = Field(..., description="智能体名称", max_length=100)
    description: str = Field("", description="智能体描述")
    system_prompt: str = Field(..., description="系统提示词")
    agent_type: str = Field("single", description="智能体类型：single, multi")
    icon: Optional[str] = Field(None, description="图标")


class CreateAgentOutput(BaseModel):
    """创建智能体输出"""
    success: bool
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    message: str = ""


class UpdateAgentInput(BaseModel):
    """更新智能体"""
    agent_id: str = Field(..., description="智能体 ID")
    name: Optional[str] = Field(None, description="智能体名称")
    description: Optional[str] = Field(None, description="智能体描述")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    is_enabled: Optional[bool] = Field(None, description="是否启用")


class UpdateAgentOutput(BaseModel):
    """更新智能体输出"""
    success: bool
    message: str = ""


class DeleteAgentInput(BaseModel):
    """删除智能体"""
    agent_id: str = Field(..., description="智能体 ID")


class DeleteAgentOutput(BaseModel):
    """删除智能体输出"""
    success: bool
    message: str = ""


class GetAgentPlazaInput(BaseModel):
    """获取智能体广场"""
    category: Optional[str] = Field(None, description="分类过滤")
    limit: int = Field(20, description="返回数量限制")


class GetAgentPlazaOutput(BaseModel):
    """智能体广场输出"""
    success: bool
    items: List[dict] = []
    total: int = 0
    message: str = ""


# ========== 工具函数 ==========

async def list_agents_tool(
    db: AsyncSession,
    user_id: int,
    agent_type: Optional[str] = None,
    include_public: bool = True,
    limit: int = 20,
) -> ListAgentsOutput:
    """获取智能体列表"""
    try:
        query = select(AgentConfig).order_by(AgentConfig.created_at.desc()).limit(limit)

        # 过滤条件
        conditions = [AgentConfig.user_id == user_id]
        if include_public:
            conditions.append(AgentConfig.is_public == True)

        query = query.where(*conditions)

        if agent_type:
            query = query.where(AgentConfig.agent_type == agent_type)

        result = await db.execute(query)
        agents = list(result.scalars().all())

        items = []
        for a in agents:
            items.append({
                "id": str(a.id),
                "name": a.name,
                "description": a.description,
                "agent_type": a.agent_type,
                "icon": a.icon,
                "is_public": a.is_public,
                "is_enabled": a.is_enabled,
                "created_at": str(a.created_at) if hasattr(a, "created_at") else None,
            })

        return ListAgentsOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"共 {len(items)} 个智能体",
        )
    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        return ListAgentsOutput(success=False, message=f"获取失败：{str(e)}")


async def get_agent_tool(
    db: AsyncSession,
    agent_id: str,
) -> GetAgentOutput:
    """获取智能体详情"""
    try:
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.id == int(agent_id))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return GetAgentOutput(success=False, message="智能体不存在")

        return GetAgentOutput(
            success=True,
            agent_info={
                "id": str(agent.id),
                "name": agent.name,
                "description": agent.description,
                "icon": agent.icon,
                "agent_type": agent.agent_type,
                "system_prompt": agent.system_prompt,
                "memory_type": agent.memory_type,
                "memory_ttl_hours": agent.memory_ttl_hours,
                "max_memory_turns": agent.max_memory_turns,
                "enabled_skills": agent.enabled_skills,
                "mcp_servers": agent.mcp_servers,
                "retrieval_enabled": agent.retrieval_enabled,
                "retrieval_top_k": agent.retrieval_top_k,
                "kb_ids": agent.kb_ids,
                "is_public": agent.is_public,
                "is_enabled": agent.is_enabled,
            },
            message=f"智能体：{agent.name}",
        )
    except Exception as e:
        logger.error(f"Failed to get agent: {e}")
        return GetAgentOutput(success=False, message=f"获取失败：{str(e)}")


async def create_agent_tool(
    db: AsyncSession,
    user_id: int,
    tenant_id: Optional[str],
    name: str,
    description: str,
    system_prompt: str,
    agent_type: str = "single",
    icon: Optional[str] = None,
) -> CreateAgentOutput:
    """创建智能体"""
    try:
        service = AgentConfigService(db)

        agent = await service.create(
            user_id=user_id,
            tenant_id=tenant_id,
            data=AgentCreate(
                name=name,
                description=description,
                icon=icon,
                agent_type=agent_type,
                system_prompt=system_prompt,
                enabled_skills=[],
                mcp_servers=[],
                memory_type="conversation",
                retrieval_enabled=False,
                is_public=False,
            ),
        )

        return CreateAgentOutput(
            success=True,
            agent_id=str(agent.id),
            agent_name=agent.name,
            message=f"智能体 '{agent.name}' 创建成功",
        )
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        return CreateAgentOutput(success=False, message=f"创建失败：{str(e)}")


async def update_agent_tool(
    db: AsyncSession,
    agent_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    system_prompt: Optional[str] = None,
    is_enabled: Optional[bool] = None,
) -> UpdateAgentOutput:
    """更新智能体"""
    try:
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.id == int(agent_id))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return UpdateAgentOutput(success=False, message="智能体不存在")

        # 更新字段
        if name:
            agent.name = name
        if description:
            agent.description = description
        if system_prompt:
            agent.system_prompt = system_prompt
        if is_enabled is not None:
            agent.is_enabled = is_enabled

        await db.commit()

        return UpdateAgentOutput(
            success=True,
            message=f"智能体 '{agent.name}' 更新成功",
        )
    except Exception as e:
        logger.error(f"Failed to update agent: {e}")
        await db.rollback()
        return UpdateAgentOutput(success=False, message=f"更新失败：{str(e)}")


async def delete_agent_tool(
    db: AsyncSession,
    agent_id: str,
) -> DeleteAgentOutput:
    """删除智能体"""
    try:
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.id == int(agent_id))
        )
        agent = result.scalar_one_or_none()

        if not agent:
            return DeleteAgentOutput(success=False, message="智能体不存在")

        await db.delete(agent)
        await db.commit()

        return DeleteAgentOutput(
            success=True,
            message=f"智能体 '{agent.name}' 已删除",
        )
    except Exception as e:
        logger.error(f"Failed to delete agent: {e}")
        await db.rollback()
        return DeleteAgentOutput(success=False, message=f"删除失败：{str(e)}")


async def get_agent_plaza_tool(
    db: AsyncSession,
    category: Optional[str] = None,
    limit: int = 20,
) -> GetAgentPlazaOutput:
    """获取智能体广场（公共智能体）"""
    try:
        query = select(AgentConfig).where(
            AgentConfig.is_public == True,
            AgentConfig.is_enabled == True,
        ).order_by(AgentConfig.created_at.desc()).limit(limit)

        if category:
            # 可以通过 description 或 name 过滤
            query = query.where(AgentConfig.name.ilike(f"%{category}%"))

        result = await db.execute(query)
        agents = list(result.scalars().all())

        items = []
        for a in agents:
            items.append({
                "id": str(a.id),
                "name": a.name,
                "description": a.description,
                "icon": a.icon,
                "agent_type": a.agent_type,
                "enabled_skills": a.enabled_skills,
            })

        return GetAgentPlazaOutput(
            success=True,
            items=items,
            total=len(items),
            message=f"智能体广场共 {len(items)} 个智能体",
        )
    except Exception as e:
        logger.error(f"Failed to get agent plaza: {e}")
        return GetAgentPlazaOutput(success=False, message=f"获取失败：{str(e)}")


# ========== LangChain 工具封装 ==========

def get_agent_tools(db: AsyncSession, user_id: int, tenant_id: Optional[str] = None) -> list:
    """获取智能体管理工具集"""
    from langchain_core.tools import StructuredTool
    import asyncio

    def _wrapper(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return [
        StructuredTool.from_function(
            func=lambda agent_type=None, include_public=True, limit=20: _wrapper(
                list_agents_tool, db, user_id, agent_type, include_public, limit
            ),
            name="list_agents",
            description="获取智能体列表",
            args_schema=ListAgentsInput,
        ),
        StructuredTool.from_function(
            func=lambda agent_id: _wrapper(
                get_agent_tool, db, agent_id
            ),
            name="get_agent",
            description="获取智能体详情",
            args_schema=GetAgentInput,
        ),
        StructuredTool.from_function(
            func=lambda name, description, system_prompt, agent_type="single", icon=None: _wrapper(
                create_agent_tool, db, user_id, tenant_id, name, description, system_prompt, agent_type, icon
            ),
            name="create_agent",
            description="创建新智能体",
            args_schema=CreateAgentInput,
        ),
        StructuredTool.from_function(
            func=lambda agent_id, name=None, description=None, system_prompt=None, is_enabled=None: _wrapper(
                update_agent_tool, db, agent_id, name, description, system_prompt, is_enabled
            ),
            name="update_agent",
            description="更新智能体配置",
            args_schema=UpdateAgentInput,
        ),
        StructuredTool.from_function(
            func=lambda agent_id: _wrapper(
                delete_agent_tool, db, agent_id
            ),
            name="delete_agent",
            description="删除智能体",
            args_schema=DeleteAgentInput,
        ),
        StructuredTool.from_function(
            func=lambda category=None, limit=20: _wrapper(
                get_agent_plaza_tool, db, category, limit
            ),
            name="get_agent_plaza",
            description="获取智能体广场（公共智能体）",
            args_schema=GetAgentPlazaInput,
        ),
    ]
