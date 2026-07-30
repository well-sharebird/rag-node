"""
Agent Orchestration Service - 智能体编排服务统一入口

设计原则：
- 统一使用 AgentFactory.execute() 作为执行入口
- 所有 Agent 创建都通过 AgentFactory.create_agent()
"""
import logging
from typing import Optional, Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_factory import AgentFactory
from app.core.tracing import trace_execution

logger = logging.getLogger("app.services.agent_orchestration")


class AgentOrchestrationService:
    """智能体编排服务 - 统一执行入口"""

    def __init__(self, db: AsyncSession, model_gateway: Any, skill_registry: Any):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.agent_factory = AgentFactory(db, model_gateway, skill_registry)

    # ============================================================
    # Agent 执行入口 (统一使用 AgentFactory)
    # ============================================================

    async def execute_agent(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        runtime_config: Optional[dict] = None,
    ) -> dict:
        """执行 Agent 的统一入口"""
        logger.info(
            "[Orchestration] Executing Agent | agent=%s user=%s",
            agent_id, user_id
        )

        # 使用追踪上下文包裹整个执行流程（追踪服务已全局初始化）
        async with trace_execution(
            execution_type="agent_execution",
            execution_id=agent_id,
            user_id=user_id,
        ) as trace_ctx:

            result = await self.agent_factory.execute(
                agent_id=agent_id,
                user_id=user_id,
                query=query,
                runtime_config=runtime_config or {},
            )

            logger.info(
                "[Orchestration] Agent completed | run=%s",
                result.get("run_id")
            )

            return result

    async def execute_agent_stream(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        runtime_config: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """流式执行 Agent"""
        from langchain_core.messages import HumanMessage
        from app.core.database import engine
        from sqlalchemy.orm import sessionmaker
        from app.services.agent_checkpoint_service import DatabaseCheckpointSaver

        # 使用追踪上下文包裹整个执行流程（追踪服务已全局初始化）
        async with trace_execution(
            execution_type="agent_execution",
            execution_id=agent_id,
            user_id=user_id,
        ) as trace_ctx:

            agent_config = await self._get_agent_config(agent_id)
            if not agent_config:
                raise ValueError(f"Agent not found: {agent_id}")

            agent = await self.agent_factory.create_agent(agent_config, runtime_config or {})

            sync_session_factory = sessionmaker(bind=engine.sync_engine)
            sync_db = sync_session_factory()

            try:
                checkpoint_saver = DatabaseCheckpointSaver(sync_db)
                config = {
                    "configurable": {
                        "thread_id": f"{user_id}:{agent_id}:default",
                        "checkpoint_saver": checkpoint_saver,
                    }
                }

                last_content = ""  # 跟踪最后发送的内容

                # 使用 messages 模式获取流式更新
                async for event, metadata in agent.astream(
                    {"messages": [HumanMessage(content=query)]},
                    config=config,
                    stream_mode="messages",
                ):
                    # 跳过 tool 消息
                    if hasattr(event, 'type') and event.type == 'tool':
                        continue

                    # 提取内容
                    content = ""
                    if hasattr(event, 'content'):
                        content = event.content if event.content else ""

                    # 只发送新的增量内容
                    if content and content != last_content:
                        # 如果是累积式的，只发送新增部分
                        if isinstance(content, str) and content.startswith(last_content):
                            new_content = content[len(last_content):]
                            if new_content:
                                yield new_content
                                last_content = content
                        else:
                            yield content
                            last_content = content
            finally:
                sync_db.close()

    async def _get_agent_config(self, agent_id: str):
        """获取 Agent 配置"""
        from sqlalchemy import select
        from app.models.agent import AgentConfig

        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        return result.scalar_one_or_none()


async def create_orchestration_service(
    db: AsyncSession,
    model_gateway: Any,
    skill_registry: Any,
) -> AgentOrchestrationService:
    """创建编排服务实例"""
    return AgentOrchestrationService(db, model_gateway, skill_registry)
