"""
Meta Agent Service
创建和管理 Meta Agent（自主智能体）
"""
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ============================================================
# Meta Agent 系统提示词
# ============================================================

META_AGENT_SYSTEM_PROMPT = """你是一个智能体创建和管理助手 (Meta Agent)，拥有自主决策能力。

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

### 2. 决策：创建 or 使用现有智能体
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
- 创建一个"产品经理"智能体，使用产品相关的 system_prompt
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
- `execute_agent(agent_id, query, kb_ids, top_k, enable_rerank, model_name)` - 执行现有智能体
- `list_agents(status)` - 查询现有智能体列表

## RAG 检索增强

当用户问题需要检索知识库时：
- 如果用户已绑定知识库，使用 `kb_ids` 参数传递给 `execute_agent`
- 如果用户未绑定知识库，但问题需要检索，可以先调用 `list_agents` 查找有知识库访问权限的智能体

## 回答风格

- 主动思考，自主决策
- 清晰地解释你的决策过程
- 创建智能体时，生成专业、详细的 system_prompt
- 整合多个智能体结果时，提供统一的总结"""


# ============================================================
# Meta Agent 工厂
# ============================================================

class MetaAgentFactory:
    """
    Meta Agent 工厂
    创建自主智能体，可以自主调用工具完成任务
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[list[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
    ):
        self.db = db
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.kb_ids = kb_ids
        self.top_k = top_k
        self.enable_rerank = enable_rerank
        self.model_name = model_name

    async def create_meta_agent(self) -> Any:
        """
        创建 Meta Agent

        Returns:
            编译后的 LangGraph Agent
        """
        from langchain.agents import create_agent
        from langchain_core.messages import BaseMessage
        from typing import TypedDict, List, Dict, Any
        from typing_extensions import NotRequired

        # 1. 创建工具 - 传入 RAG 配置
        from packages.agent.tools.meta_agent_tools import (
            create_create_agent_tool,
            create_execute_agent_tool,
            create_list_agents_tool,
        )

        tools = [
            create_create_agent_tool(self.db, self.user_id, self.tenant_id),
            create_execute_agent_tool(
                self.db,
                self.user_id,
                kb_ids=self.kb_ids,
                top_k=self.top_k,
                enable_rerank=self.enable_rerank,
                model_name=self.model_name,
            ),
            create_list_agents_tool(self.db, self.user_id),
        ]

        # 2. 创建模型
        from packages.model_gateway.services.model_gateway_service import ModelGatewayService
        from packages.agent.services.agent_runtime_service import create_langchain_llm
        from packages.agent.schemas.chat import ModelConfig

        model_gateway = ModelGatewayService(self.db)

        # 使用本地 Qwen 模型
        model_config = ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            api_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )

        llm = await create_langchain_llm(model_config, self.db)
        llm_with_tools = llm.bind_tools(tools)

        # 3. 定义状态 - 使用 Annotated 处理多值更新
        from typing_extensions import Annotated
        from langgraph.graph.message import add_messages

        class MetaAgentState(TypedDict):
            messages: Annotated[List[BaseMessage], add_messages]
            context: Dict[str, Any]
            created_agents: List[str]
            agents_used: List[str]

        # 4. 创建 Agent
        agent = create_agent(
            model=llm_with_tools,
            tools=tools,
            system_prompt=META_AGENT_SYSTEM_PROMPT,
            state_schema=MetaAgentState,
        )

        logger.info("[MetaAgentFactory] Meta Agent created with tools: %s", [t.name for t in tools])

        return agent


# ============================================================
# Meta Agent 服务
# ============================================================

class MetaAgentService:
    """
    Meta Agent 服务
    提供 Meta Agent 的执行接口
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[list[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
    ):
        self.db = db
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.kb_ids = kb_ids
        self.top_k = top_k
        self.enable_rerank = enable_rerank
        self.model_name = model_name

    async def execute(
        self,
        query: str,
        kb_ids: Optional[list[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
    ) -> dict:
        """
        执行 Meta Agent

        Args:
            query: 用户输入/查询
            kb_ids: 知识库 ID 列表（可选）
            top_k: 检索返回的文档片段数量
            enable_rerank: 是否启用重排序
            model_name: 运行时选择的模型名称

        Returns:
            执行结果
        """
        # 创建 Meta Agent - 传入配置（优先使用调用时传入的参数）
        factory = MetaAgentFactory(
            self.db,
            self.user_id,
            self.tenant_id,
            kb_ids=kb_ids or self.kb_ids,
            top_k=top_k,
            enable_rerank=enable_rerank or self.enable_rerank,
            model_name=model_name or self.model_name,
        )
        agent = await factory.create_meta_agent()

        # 执行
        from langchain_core.messages import HumanMessage
        result = await agent.ainvoke({
            "messages": [HumanMessage(content=query)]
        })

        # 提取响应
        messages = result.get("messages", [])
        response = ""
        for msg in reversed(messages):
            if hasattr(msg, 'content') and msg.content:
                response = msg.content
                break

        return {
            "response": response,
            "messages": messages,
            "agents_used": result.get("agents_used", []),
        }

    async def execute_stream(
        self,
        query: str,
        kb_ids: Optional[list[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
    ):
        """
        流式执行 Meta Agent

        Args:
            query: 用户输入
            kb_ids: 知识库 ID 列表（可选）
            top_k: 检索返回的文档片段数量
            enable_rerank: 是否启用重排序
            model_name: 运行时选择的模型名称

        Yields:
            流式响应的 token
        """
        # 创建 Meta Agent - 传入配置（优先使用调用时传入的参数）
        factory = MetaAgentFactory(
            self.db,
            self.user_id,
            self.tenant_id,
            kb_ids=kb_ids or self.kb_ids,
            top_k=top_k,
            enable_rerank=enable_rerank or self.enable_rerank,
            model_name=model_name or self.model_name,
        )
        agent = await factory.create_meta_agent()

        from langchain_core.messages import HumanMessage
        from langchain_core.messages import AIMessageChunk

        async for event, metadata in agent.astream(
            {"messages": [HumanMessage(content=query)]},
            stream_mode="messages",
        ):
            if isinstance(event, AIMessageChunk) and event.content:
                yield event.content


# ============================================================
# 便捷函数
# ============================================================

async def create_meta_agent_service(
    db: AsyncSession,
    user_id: int,
    tenant_id: str,
) -> MetaAgentService:
    """创建 Meta Agent 服务实例"""
    return MetaAgentService(db, user_id, tenant_id)
