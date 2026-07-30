"""
Agent Factory - 统一的 Agent 工厂

根据数据库配置动态创建 Agent，统一使用 create_agent() 模式。

设计原则（参考 DeerFlow）：
1. 统一使用 create_agent() 工厂函数创建所有 Agent
2. StateGraph 仅用于特殊复杂工作流（本系统默认不使用）
3. 通过中间件链扩展 Agent 行为
4. 配置驱动：从数据库加载配置后立即创建

架构设计：
┌─────────────────────────────────────────────────────────────┐
│                     AgentFactory                             │
│                                                              │
│  create_agent(agent_config, runtime_config)                 │
│      │                                                       │
│      ├─ 1. 加载模型 (ModelLoader)                            │
│      ├─ 2. 加载工具 (ToolLoader)                             │
│      ├─ 3. 构建中间件 (MiddlewareBuilder)                    │
│      └─ 4. create_agent() → CompiledGraph                    │
│                                                              │
│  execute(agent_id, user_id, query, runtime_config)          │
│      │                                                       │
│      ├─ 从数据库获取 AgentConfig                             │
│      ├─ create_agent() 动态创建                              │
│      └─ agent.ainvoke() 执行                                 │
└─────────────────────────────────────────────────────────────┘
"""
import logging
from typing import Any, Optional, Callable
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import AgentConfig
from app.schemas.chat import ModelConfig

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    统一的 Agent 工厂 - 根据数据库配置动态创建 Agent

    核心特性：
    1. 配置驱动：从数据库读取 AgentConfig 后立即创建
    2. 统一模式：所有 Agent 都使用 create_agent()
    3. 多 Agent 支持：主 Agent 通过 task 工具调用子 Agent
    4. 运行时覆盖：支持运行时修改模型、工具等配置
    """

    def __init__(self, db: AsyncSession, model_gateway: Any, skill_registry: Any):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self._subagent_cache: dict[str, dict[str, AgentConfig]] = {}

    async def create_agent(
        self,
        agent_config: AgentConfig,
        runtime_config: Optional[dict] = None,
    ) -> Any:
        """
        根据 AgentConfig 动态创建 Agent

        Args:
            agent_config: 从数据库获取的 Agent 配置
            runtime_config: 运行时覆盖配置
                {
                    "model_name": str,
                    "plan_mode": bool,
                    "skills": list[str],
                    "mcp_servers": list[str],
                    "tools": list,
                }

        Returns:
            Compiled LangGraph Agent
        """
        runtime_config = runtime_config or {}

        logger.info(
            "[AgentFactory] Creating agent | name=%s type=%s id=%s",
            agent_config.name, agent_config.agent_type, agent_config.id
        )

        # 1. 加载模型（运行时覆盖优先）
        model_name = runtime_config.get("model_name")
        if model_name:
            model_config = await self.model_gateway.get_model_by_name(model_name)
            if model_config:
                llm = await self._create_llm(model_config)
            else:
                logger.warning("Model '%s' not found, using default", model_name)
                llm = await self._create_llm_from_dict(agent_config.default_model_config)
        else:
            llm = await self._create_llm_from_dict(agent_config.default_model_config)

        # 2. 加载工具
        tools = await self._load_tools_for_agent(agent_config, runtime_config)

        # 3. 绑定工具到模型
        llm_with_tools = llm.bind_tools(tools)

        # 4. 构建中间件
        middlewares = self._build_middlewares(agent_config, runtime_config)

        # 5. 创建 Agent (核心：统一用 create_agent)
        agent = create_agent(
            model=llm_with_tools,
            tools=tools,
            middleware=middlewares,
            system_prompt=agent_config.system_prompt,
            state_schema=self._get_state_schema(agent_config),
        )

        logger.info(
            "[AgentFactory] Agent created | name=%s tools=%d",
            agent_config.name, len(tools)
        )

        return agent

    async def _create_llm(self, model_config: ModelConfig) -> Any:
        """从 ModelConfig 创建 LLM"""
        from app.services.agent_runtime_service import create_langchain_llm
        return await create_langchain_llm(model_config, self.db)

    async def _create_llm_from_dict(self, config_dict: Optional[dict]) -> Any:
        """从字典配置创建 LLM"""
        if not config_dict:
            # 回退到默认模型
            logger.warning("No model config, using default model")
            config_dict = {
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            }

        model_config = ModelConfig(**config_dict)
        return await self._create_llm(model_config)

    async def _load_tools_for_agent(
        self,
        agent_config: AgentConfig,
        runtime_config: dict,
    ) -> list:
        tools = []

        # 1. 基础工具
        tools.extend(await self._load_basic_tools())

        # 2. 特殊 Agent：智能体助手（添加管理工具）
        if agent_config.name == "智能体助手":
            management_tools = await self._load_agent_management_tools()
            tools.extend(management_tools)

        # 3. RAG 检索工具（当配置了 kb_ids 时）
        kb_ids = runtime_config.get("kb_ids", agent_config.kb_ids or [])
        if kb_ids:
            rag_tool = await self._create_rag_tool(kb_ids, runtime_config)
            tools.append(rag_tool)

        # 4. MCP 工具
        mcp_servers = runtime_config.get("mcp_servers", agent_config.mcp_servers or [])
        if mcp_servers:
            mcp_tools = await self._load_mcp_tools(mcp_servers)
            tools.extend(mcp_tools)

        # 5. 技能工具
        enabled_skills = runtime_config.get("skills", agent_config.enabled_skills or [])
        if enabled_skills:
            skill_tools = await self._load_skill_tools(enabled_skills)
            tools.extend(skill_tools)

        # 6. 多 Agent 配置添加 task 工具
        if agent_config.agent_type == "multi":
            task_tool = await self._create_task_tool(agent_config)
            tools.append(task_tool)

        # 7. 运行时覆盖
        if runtime_config.get("tools"):
            tools = runtime_config["tools"]

        return tools

    async def _load_agent_management_tools(self) -> list:
        """加载智能体管理工具（create_agent, execute_agent, list_agents）"""
        from app.tools.meta_agent_tools import (
            create_create_agent_tool,
            create_execute_agent_tool,
            create_list_agents_tool,
        )

        # 使用默认用户 ID（系统级）
        return [
            create_create_agent_tool(self.db, user_id=1, tenant_id="system"),
            create_execute_agent_tool(self.db, user_id=1),
            create_list_agents_tool(self.db, user_id=1),
        ]

    async def _load_basic_tools(self) -> list:
        """加载基础工具"""
        from app.tools.builtins import get_basic_tools
        return await get_basic_tools()

    async def _create_rag_tool(self, kb_ids: list[str], runtime_config: dict) -> Callable:
        """
        创建 RAG 检索工具

        Args:
            kb_ids: 知识库 ID 列表
            runtime_config: 运行时配置（包含 top_k, enable_rerank 等）

        Returns:
            LangChain 工具
        """
        from langchain_core.tools import tool
        from app.services.retrieval_service import search_chunks
        from app.schemas.retrieval import SearchRequest
        from app.core.milvus_client import get_milvus_client
        from app.core.redis_client import get_redis
        import redis.asyncio as aioredis

        top_k = runtime_config.get("top_k", 5)
        enable_rerank = runtime_config.get("enable_rerank", False)

        @tool
        async def search_knowledge_base(query: str) -> str:
            """
            Search the knowledge base for relevant information.

            Use this tool when:
            - You need to find information from the knowledge base
            - The user's question requires retrieving context from documents
            - You need to provide citations for your answer

            Args:
                query: The search query

            Returns:
            Retrieved context from the knowledge base with source information
            """
            logger.info(
                "[RAG Tool] Searching knowledge base | query=%s kb_ids=%s top_k=%s",
                query, kb_ids, top_k
            )

            try:
                milvus = get_milvus_client()
                redis_client = await get_redis()

                # 为每个 kb_id 执行搜索
                all_results = []
                for kb_id in kb_ids:
                    request = SearchRequest(
                        kb_id=kb_id,
                        query=query,
                        top_k=top_k,
                        enable_rerank=enable_rerank,
                    )
                    response = await search_chunks(self.db, redis_client, milvus, request)

                    for item in response.results:
                        all_results.append({
                            "content": item.content,
                            "doc_name": item.metadata.get("doc_name", "Unknown"),
                            "doc_id": item.metadata.get("doc_id", ""),
                            "score": item.score,
                        })

                # 格式化结果
                formatted_results = []
                for i, result in enumerate(all_results[:top_k], 1):
                    formatted_results.append(
                        f"[{i}] {result['content']}\n    来源：{result.get('doc_name', 'Unknown')}"
                    )

                return "\n\n".join(formatted_results) if formatted_results else "未找到相关内容"

            except Exception as e:
                logger.exception("[RAG Tool] Search failed")
                return f"检索失败：{str(e)}"

        return search_knowledge_base

    async def _load_mcp_tools(self, mcp_servers: list[str]) -> list:
        """加载 MCP 工具"""
        # TODO: 实现 MCP 工具加载
        logger.warning("MCP tools not implemented yet")
        return []

    async def _load_skill_tools(self, skills: list[str]) -> list:
        """加载技能工具"""
        # TODO: 使用 skill_registry 加载技能
        logger.warning("Skill tools not implemented yet")
        return []

    def _build_middlewares(
        self,
        agent_config: AgentConfig,
        runtime_config: dict,
    ) -> list:
        middlewares = []

        # 计划模式中间件
        if runtime_config.get("plan_mode", False):
            from app.agents.middlewares.plan_middleware import PlanMiddleware
            middlewares.append(PlanMiddleware())

        # 日志中间件（始终启用）
        middlewares.append(LoggingMiddleware(
            agent_id=str(agent_config.id),
            agent_name=agent_config.name,
        ))

        return middlewares

    def _get_state_schema(self, agent_config: AgentConfig) -> type:
        from typing import TypedDict, List, Dict, Any
        from typing_extensions import NotRequired
        from langchain_core.messages import BaseMessage

        class AgentState(TypedDict, total=False):
            messages: List[BaseMessage]
            context: Dict[str, Any]
            metadata: Dict[str, Any]
            plan: NotRequired[List[str]]
            todo_list: NotRequired[List[Dict[str, Any]]]
            subagent_results: NotRequired[Dict[str, Any]]

        return AgentState

    async def _create_task_tool(self, parent_config: AgentConfig) -> Callable:
        """
        创建 task 工具，用于多 Agent 场景

        Args:
            parent_config: 主 Agent 配置

        Returns:
            LangChain 工具
        """

        @tool
        async def delegate_to_subagent(
            task_description: str,
            subagent_type: str,
            expected_output: str,
        ) -> str:
            """
            Delegate a task to a specialized subagent.

            Use this tool when:
            - The task requires specialized expertise
            - The task should be handled by a dedicated agent
            - You need to coordinate multiple steps of work

            Args:
                task_description: Clear description of what needs to be done
                subagent_type: Type of subagent needed (e.g., "code_reviewer", "doc_writer")
                expected_output: Description of the expected output format

            Returns:
                The subagent's execution result
            """
            logger.info(
                "[TaskTool] Delegating task | type=%s parent=%s",
                subagent_type, parent_config.name
            )

            try:
                # 1. 获取子 Agent 配置
                subagent_config = await self._get_subagent_config(
                    parent_config.id,
                    subagent_type,
                )

                if not subagent_config:
                    return f"[ERROR] Subagent '{subagent_type}' not found"

                # 2. 递归创建子 Agent (又是 create_agent!)
                subagent = await self.create_agent(subagent_config)

                # 3. 执行子 Agent
                result = await subagent.ainvoke({
                    "messages": [
                        HumanMessage(
                            content=f"{task_description}\n\nExpected output: {expected_output}"
                        )
                    ]
                })

                # 4. 提取响应
                response = self._extract_response(result)

                logger.info(
                    "[TaskTool] Subagent completed | type=%s",
                    subagent_type
                )

                return response

            except Exception as e:
                logger.exception(
                    "[TaskTool] Subagent execution failed | type=%s",
                    subagent_type
                )
                return f"[ERROR] Subagent failed: {str(e)}"

        # 设置工具元数据
        delegate_to_subagent.name = "delegate_to_subagent"
        delegate_to_subagent.description = """
Delegate a task to a specialized subagent for execution.

Use this tool when:
- The task requires specialized expertise (code analysis, document writing, research)
- The task is complex and should be handled by a dedicated agent
- You need to coordinate multiple steps of work

Args:
    task_description: Clear description of what needs to be done
    subagent_type: Type of subagent needed (code_reviewer, doc_writer, researcher, etc.)
    expected_output: Description of the expected output format

Returns:
    The subagent's execution result
"""

        return delegate_to_subagent

    async def _get_subagent_config(
        self,
        parent_id: str,
        subagent_type: str,
    ) -> Optional[AgentConfig]:
        """获取子 Agent 配置"""
        # 检查缓存
        if parent_id in self._subagent_cache:
            return self._subagent_cache[parent_id].get(subagent_type)

        # 从数据库查询子 Agent
        result = await self.db.execute(
            select(AgentConfig)
            .where(AgentConfig.user_id == 1)  # TODO: 根据实际 schema 查询
        )

        configs = result.scalars().all()

        # 构建缓存
        self._subagent_cache[parent_id] = {cfg.name: cfg for cfg in configs}
        return self._subagent_cache[parent_id].get(subagent_type)

    def _extract_response(self, result: dict) -> str:
        """
        从执行结果中提取响应

        Args:
            result: Agent 执行结果

        Returns:
            响应文本
        """
        messages = result.get("messages", [])
        if not messages:
            return ""

        # 找到最后一个 AIMessage
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # 处理列表格式的内容
                    text_parts = []
                    for block in content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict) and "text" in block:
                            text_parts.append(block["text"])
                    return "\n".join(text_parts)

        return ""

    async def execute(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        runtime_config: Optional[dict] = None,
    ) -> dict:
        run_id = str(uuid4())

        logger.info(
            "[AgentFactory] Executing agent | id=%s user=%s run=%s",
            agent_id, user_id, run_id
        )

        agent_config = await self._get_agent_config(agent_id)
        if not agent_config:
            raise ValueError(f"Agent not found: {agent_id}")

        agent = await self.create_agent(agent_config, runtime_config)
        result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
        response = self._extract_response(result)
        messages = result.get("messages", [])

        logger.info(
            "[AgentFactory] Agent completed | run=%s response_length=%d",
            run_id, len(response)
        )

        return {
            "run_id": run_id,
            "agent_id": agent_id,
            "agent_type": agent_config.agent_type,
            "response": response,
            "messages": messages,
        }

    async def _get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """从数据库获取 Agent 配置"""
        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        return result.scalar_one_or_none()


# ============================================================
# 中间件
# ============================================================

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime


class LoggingMiddleware(AgentMiddleware):
    """日志中间件"""

    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name

    def before_agent(self, state, runtime: Runtime):
        thread_id = runtime.context.get("thread_id", "unknown") if runtime.context else "unknown"
        logger.info(
            "[AgentRuntime] Before agent | id=%s name=%s thread=%s",
            self.agent_id, self.agent_name, thread_id
        )
        return None

    def after_agent(self, state, runtime: Runtime):
        thread_id = runtime.context.get("thread_id", "unknown") if runtime.context else "unknown"
        logger.info(
            "[AgentRuntime] After agent | id=%s name=%s thread=%s",
            self.agent_id, self.agent_name, thread_id
        )
        return None
