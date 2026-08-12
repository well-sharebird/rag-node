"""
Agent 配置服务
提供 Agent 的 CRUD 操作
"""
from __future__ import annotations
from typing import Optional, Tuple, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from packages.agent.models.agent import AgentConfig, AgentVersion
from packages.agent.schemas.chat import AgentCreate, AgentUpdate


class AgentConfigService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: int,
        tenant_id: Optional[str],
        data: AgentCreate
    ) -> AgentConfig:
        """创建新的 Agent"""
        agent = AgentConfig(
            user_id=user_id,
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            icon=data.icon,
            agent_type=data.agent_type or "single",
            default_model_config=data.default_model_config,
            system_prompt=data.system_prompt,
            enabled_skills=data.enabled_skills or [],
            mcp_servers=data.mcp_servers or [],
            memory_type=data.memory_type or "conversation",
            memory_ttl_hours=data.memory_ttl_hours or 24,
            max_memory_turns=data.max_memory_turns or 50,
            kb_ids=data.kb_ids or [],
            retrieval_top_k=data.retrieval_top_k or 5,
            retrieval_enabled=data.retrieval_enabled or False,
            multi_agent_config=data.multi_agent_config,
            security_policy=data.security_policy,
            is_public=data.is_public or False,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_by_id(self, agent_id: str, user_id: Optional[int] = None) -> Optional[AgentConfig]:
        """根据 ID 获取 Agent"""
        query = select(AgentConfig).where(AgentConfig.id == agent_id)
        if user_id:
            query = query.where(AgentConfig.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        user_id: int,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[AgentConfig], int]:
        """获取用户的 Agent 列表"""
        query = select(AgentConfig).where(AgentConfig.user_id == user_id)

        if status:
            query = query.where(AgentConfig.status == status)
        if agent_type:
            query = query.where(AgentConfig.agent_type == agent_type)

        # 获取总数
        count_query = select(func.count(AgentConfig.id)).where(AgentConfig.user_id == user_id)
        if status:
            count_query = count_query.where(AgentConfig.status == status)
        if agent_type:
            count_query = count_query.where(AgentConfig.agent_type == agent_type)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(desc(AgentConfig.updated_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        agents = result.scalars().all()
        return list(agents), total

    async def list_public(
        self,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[AgentConfig], int]:
        """获取广场公开的 Agent"""
        query = select(AgentConfig).where(
            AgentConfig.is_public == True,
            AgentConfig.status == "active"
        )
        count_query = select(func.count(AgentConfig.id)).where(
            AgentConfig.is_public == True,
            AgentConfig.status == "active"
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(AgentConfig.total_runs)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        agents = result.scalars().all()
        return list(agents), total

    async def update(
        self,
        agent_id: str,
        user_id: int,
        data: AgentUpdate,
        create_version: bool = False
    ) -> Optional[AgentConfig]:
        """更新 Agent 配置"""
        agent = await self.get_by_id(agent_id, user_id)
        if not agent:
            return None

        # 创建版本快照（如果需要）
        if create_version and agent.status == "active":
            await self._create_version(agent, data)

        # 更新字段
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(agent, field):
                setattr(agent, field, value)

        agent.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent_id: str, user_id: int) -> bool:
        """删除 Agent"""
        agent = await self.get_by_id(agent_id, user_id)
        if not agent:
            return False
        await self.db.delete(agent)
        await self.db.commit()
        return True

    async def publish(self, agent_id: str, user_id: int) -> Optional[AgentConfig]:
        """发布 Agent"""
        agent = await self.get_by_id(agent_id, user_id)
        if not agent:
            return None
        agent.status = "active"
        agent.published_at = datetime.utcnow()
        # 创建初始版本
        await self._create_version(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def unpublish(self, agent_id: str, user_id: int) -> Optional[AgentConfig]:
        """取消发布 Agent"""
        agent = await self.get_by_id(agent_id, user_id)
        if not agent:
            return None
        agent.status = "draft"
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def duplicate(self, agent_id: str, user_id: int, tenant_id: Optional[str]) -> Optional[AgentConfig]:
        """复制 Agent"""
        source = await self.get_by_id(agent_id)
        if not source:
            return None

        agent = AgentConfig(
            user_id=user_id,
            tenant_id=tenant_id,
            name=f"{source.name} (副本)",
            description=source.description,
            icon=source.icon,
            agent_type=source.agent_type,
            default_model_config=source.default_model_config,
            system_prompt=source.system_prompt,
            enabled_skills=source.enabled_skills,
            mcp_servers=source.mcp_servers,
            memory_type=source.memory_type,
            memory_ttl_hours=source.memory_ttl_hours,
            max_memory_turns=source.max_memory_turns,
            kb_ids=source.kb_ids,
            retrieval_top_k=source.retrieval_top_k,
            retrieval_enabled=source.retrieval_enabled,
            multi_agent_config=source.multi_agent_config,
            status="draft",
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def _create_version(self, agent: AgentConfig, update_data: Optional[AgentUpdate] = None):
        """创建版本快照"""
        # 计算新版本号
        last_version_result = await self.db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(desc(AgentVersion.created_at))
            .limit(1)
        )
        last_version = last_version_result.scalar_one_or_none()

        if last_version:
            major, minor, patch = map(int, last_version.version.split('.'))
            new_version = f"{major}.{minor + 1}.{patch}"
        else:
            new_version = "1.0.0"

        # 构建配置快照
        config_snapshot = {
            "name": agent.name,
            "description": agent.description,
            "icon": agent.icon,
            "agent_type": agent.agent_type,
            "default_model_config": agent.default_model_config,
            "system_prompt": agent.system_prompt,
            "enabled_skills": agent.enabled_skills,
            "mcp_servers": agent.mcp_servers,
            "memory_type": agent.memory_type,
            "memory_ttl_hours": agent.memory_ttl_hours,
            "max_memory_turns": agent.max_memory_turns,
            "kb_ids": agent.kb_ids,
            "retrieval_top_k": agent.retrieval_top_k,
            "retrieval_enabled": agent.retrieval_enabled,
            "multi_agent_config": agent.multi_agent_config,
        }

        version = AgentVersion(
            agent_id=agent.id,
            version=new_version,
            config_snapshot=config_snapshot,
            changelog=update_data.changelog if update_data else None,
            published_by=agent.user_id,
        )
        self.db.add(version)
        agent.current_version = new_version
