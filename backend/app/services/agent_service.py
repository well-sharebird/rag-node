"""
Agent Service - 统一的智能体服务层

设计原则：
1. 统一执行入口 - 所有智能体执行都通过 AgentService
2. 配置驱动 - 从数据库动态加载配置
3. 支持多种执行模式 - 单智能体、多智能体协作、Meta Agent
4. 完整的可观测性 - 日志、追踪、统计

执行模式：
1. SINGLE - 单个智能体执行
2. MULTI - 多智能体协作（并行/串行）
3. META - Meta Agent（自主决策创建/调度智能体）
"""
import logging
import time
import asyncio
import json
from typing import Optional, Any, AsyncGenerator, Dict, List, Callable
from datetime import datetime
from uuid import uuid4
from enum import Enum
from contextlib import asynccontextmanager
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, AIMessageChunk
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, Annotated, NotRequired

from app.models.agent import AgentConfig, AgentCallLog
from app.models.user import User
from app.schemas.chat import ModelConfig
from app.core.database import engine, async_session_factory
from app.core.tracing import trace_execution
from app.services.agent_checkpoint_service import DatabaseCheckpointSaver
from app.services.agent_memory_service import AgentMemoryService
from app.services.agent_graph_factory import StateGraphBuilder, WorkflowState
from app.services.retrieval_service import search_chunks
from app.schemas.retrieval import SearchRequest

logger = logging.getLogger("app.services.agent_service")

# 同步 Session factory 用于 LangGraph CheckpointSaver
sync_session_factory = sessionmaker(bind=engine.sync_engine)


# ============================================================
# 执行模式枚举
# ============================================================

class ExecutionMode(str, Enum):
    """智能体执行模式"""
    SINGLE = "single"           # 单智能体
    MULTI = "multi"             # 多智能体协作
    META = "meta"               # Meta Agent（自主决策）
    SUPERVISOR = "supervisor"   # Supervisor 模式
    ROUND_ROBIN = "round_robin" # 轮询模式
    VOTING = "voting"           # 投票模式


# ============================================================
# 请求/响应 Schema
# ============================================================

class AgentExecuteRequest:
    """智能体执行请求"""
    def __init__(
        self,
        query: str,
        user_id: int,
        tenant_id: str,
        agent_id: Optional[str] = None,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        session_id: Optional[str] = None,
        debug_mode: bool = False,
        execution_mode: ExecutionMode = ExecutionMode.SINGLE,
        runtime_config: Optional[Dict] = None,
    ):
        self.agent_id = agent_id
        self.query = query
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.kb_ids = kb_ids
        self.top_k = top_k
        self.enable_rerank = enable_rerank
        self.model_name = model_name
        self.session_id = session_id
        self.debug_mode = debug_mode
        self.execution_mode = execution_mode
        self.runtime_config = runtime_config or {}


class AgentExecuteResult:
    """智能体执行结果"""
    def __init__(
        self,
        run_id: str,
        agent_id: Optional[str],
        response: str,
        messages: List[Any],
        agents_used: List[str] = None,
        latency_ms: int = 0,
        tokens_used: int = 0,
        created_at: Optional[datetime] = None,
        metadata: Optional[Dict] = None,
    ):
        self.run_id = run_id
        self.agent_id = agent_id
        self.response = response
        self.messages = messages or []
        self.agents_used = agents_used or []
        self.latency_ms = latency_ms
        self.tokens_used = tokens_used
        self.created_at = created_at or datetime.utcnow()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "response": self.response,
            "messages": self.messages,
            "agents_used": self.agents_used,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


# ============================================================
# 智能体工厂 - 核心创建逻辑
# ============================================================

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

        Returns:
            Compiled LangGraph Agent
        """
        from langchain.agents import create_agent as langchain_create_agent

        runtime_config = runtime_config or {}

        logger.info(
            "[AgentFactory] Creating agent | name=%s type=%s id=%s",
            agent_config.name, agent_config.agent_type, agent_config.id
        )

        # 1. 加载模型
        llm = await self._create_llm_for_agent(agent_config, runtime_config)

        # 2. 加载工具
        tools = await self._load_tools_for_agent(agent_config, runtime_config)

        # 3. 绑定工具到模型
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        # 4. 构建中间件
        middlewares = self._build_middlewares(agent_config, runtime_config)

        # 5. 创建 Agent
        agent = langchain_create_agent(
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

    async def _create_llm_for_agent(self, agent_config: AgentConfig, runtime_config: dict) -> Any:
        """创建 Agent 使用的 LLM"""
        from app.services.agent_runtime_service import create_langchain_llm

        model_name = runtime_config.get("model_name")
        if model_name:
            model_config = await self.model_gateway.get_model_by_name(model_name)
            if model_config:
                return await create_langchain_llm(model_config, self.db)
            logger.warning("Model '%s' not found, using default", model_name)

        # 使用默认配置
        config_dict = agent_config.default_model_config or {
            "provider": "local_qwen",
            "model": "qwen3.5-397b-a17b",
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        model_config = ModelConfig(**config_dict)
        return await create_langchain_llm(model_config, self.db)

    async def _load_tools_for_agent(self, agent_config: AgentConfig, runtime_config: dict) -> list:
        """加载 Agent 使用的工具"""
        tools = []

        # 1. 基础工具
        tools.extend(await self._load_basic_tools())

        # 2. 特殊 Agent：智能体助手
        if agent_config.name == "智能体助手":
            tools.extend(await self._load_agent_management_tools())

        # 3. RAG 检索工具
        kb_ids = runtime_config.get("kb_ids", agent_config.kb_ids or [])
        if kb_ids:
            rag_tool = await self._create_rag_tool(kb_ids, runtime_config)
            tools.append(rag_tool)

        # 4. MCP 工具
        mcp_servers = runtime_config.get("mcp_servers", agent_config.mcp_servers or [])
        if mcp_servers:
            tools.extend(await self._load_mcp_tools(mcp_servers))

        # 5. 技能工具
        enabled_skills = runtime_config.get("skills", agent_config.enabled_skills or [])
        if enabled_skills:
            tools.extend(await self._load_skill_tools(enabled_skills))

        # 6. 多 Agent 配置添加 task 工具
        if agent_config.agent_type == "multi":
            tools.append(await self._create_task_tool(agent_config))

        # 7. 运行时覆盖
        if runtime_config.get("tools"):
            tools = runtime_config["tools"]

        return tools

    async def _load_basic_tools(self) -> list:
        """加载基础工具"""
        from app.tools.builtins import get_basic_tools
        return await get_basic_tools()

    async def _load_agent_management_tools(self) -> list:
        """加载智能体管理工具"""
        from app.tools.meta_agent_tools import (
            create_create_agent_tool,
            create_execute_agent_tool,
            create_list_agents_tool,
        )
        return [
            create_create_agent_tool(self.db, user_id=1, tenant_id="system"),
            create_execute_agent_tool(self.db, user_id=1),
            create_list_agents_tool(self.db, user_id=1),
        ]

    async def _create_rag_tool(self, kb_ids: list[str], runtime_config: dict) -> Callable:
        """创建 RAG 检索工具"""
        from langchain_core.tools import tool
        from app.core.milvus_client import get_milvus_client
        from app.core.redis_client import get_redis

        top_k = runtime_config.get("top_k", 5)
        enable_rerank = runtime_config.get("enable_rerank", False)

        @tool
        async def search_knowledge_base(query: str) -> str:
            """Search the knowledge base for relevant information."""
            logger.info(
                "[RAG Tool] Searching knowledge base | query=%s kb_ids=%s top_k=%s",
                query, kb_ids, top_k
            )

            try:
                milvus = get_milvus_client()
                redis_client = await get_redis()

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
        from langchain_core.tools import tool
        from app.mcp_integration.tools.kb_tools import (
            list_kbs_handler as mcp_list_kbs,
            get_kb_handler as mcp_get_kb,
            create_kb_handler as mcp_create_kb,
            delete_kb_handler as mcp_delete_kb,
        )
        from app.mcp_integration.tools.model_tools import (
            list_models_handler as mcp_list_models,
            get_model_handler as mcp_get_model,
            create_model_handler as mcp_create_model,
            update_model_handler as mcp_update_model,
            delete_model_handler as mcp_delete_model,
        )
        from app.mcp_integration.tools.prompt_tools import (
            list_prompts_handler as mcp_list_prompts,
            get_prompt_handler as mcp_get_prompt,
            create_prompt_handler as mcp_create_prompt,
            update_prompt_handler as mcp_update_prompt,
        )
        from app.mcp_integration.tools.agent_tools import (
            list_agents_handler as mcp_list_agents,
            get_agent_handler as mcp_get_agent,
            create_agent_handler as mcp_create_agent_tool,
            update_agent_handler as mcp_update_agent,
            delete_agent_handler as mcp_delete_agent,
            list_public_agents_handler as mcp_get_plaza,
        )

        tools = []
        user_id = 1

        if "kb" in mcp_servers or "all" in mcp_servers:
            @tool
            async def mcp_kb_list(search: Optional[str] = None, limit: int = 50) -> str:
                """List all knowledge bases."""
                result = await mcp_list_kbs(self.db, search=search, limit=limit)
                data = result.get("data", [])
                return f"Knowledge bases: {[kb.get('name', 'Unknown') for kb in data]}"

            @tool
            async def mcp_kb_get(kb_id: str) -> str:
                """Get knowledge base details by ID."""
                result = await mcp_get_kb(self.db, kb_id)
                data = result.get("data", {})
                return f"KB info: {data}" if result.get("success") else result.get("error", "Unknown error")

            @tool
            async def mcp_kb_create(name: str, description: str = "") -> str:
                """Create a new knowledge base."""
                from app.schemas.knowledge_base import KBCreateRequest
                req = KBCreateRequest(name=name, description=description)
                result = await mcp_create_kb(self.db, req)
                return result.get("message", "Created")

            @tool
            async def mcp_kb_delete(kb_id: str) -> str:
                """Delete a knowledge base by ID."""
                result = await mcp_delete_kb(self.db, kb_id)
                return result.get("message", "Deleted")

            tools.extend([mcp_kb_list, mcp_kb_get, mcp_kb_create, mcp_kb_delete])

        # 模型、提示词、Agent 工具加载逻辑类似，此处省略以精简代码
        # 实际需要完整实现...

        return tools

    async def _load_skill_tools(self, skills: list[str]) -> list:
        """加载技能工具"""
        from langchain_core.tools import tool

        tools = []
        user_id = 1

        for skill in skills:
            skill_lower = skill.lower()

            if skill_lower in ["kb", "knowledge_base", "knowledge"]:
                from app.skills.knowledge_base_tools import (
                    list_knowledge_bases as kb_list,
                    get_knowledge_base as kb_get,
                    create_knowledge_base as kb_create,
                    delete_knowledge_base as kb_delete,
                )

                @tool
                async def skill_kb_list(search: Optional[str] = None) -> str:
                    """List all knowledge bases."""
                    result = await kb_list(self.db, user_id, search)
                    items = result.items if result.success else []
                    return f"Knowledge bases: {[kb['name'] for kb in items]}"

                tools.extend([skill_kb_list])

            # 其他技能加载逻辑...

        return tools

    def _build_middlewares(self, agent_config: AgentConfig, runtime_config: dict) -> list:
        """构建中间件链"""
        from langchain.agents.middleware import AgentMiddleware
        from langgraph.runtime import Runtime

        middlewares = []

        # 计划模式中间件
        if runtime_config.get("plan_mode", False):
            from app.agents.middlewares.plan_middleware import PlanMiddleware
            middlewares.append(PlanMiddleware())

        # 日志中间件
        class LoggingMiddleware(AgentMiddleware):
            def __init__(middleware_self):
                middleware_self.agent_id = str(agent_config.id)
                middleware_self.agent_name = agent_config.name

            def before_agent(middleware_self, state, runtime: Runtime):
                thread_id = runtime.context.get("thread_id", "unknown") if runtime.context else "unknown"
                logger.info(
                    "[AgentRuntime] Before agent | id=%s name=%s thread=%s",
                    middleware_self.agent_id, middleware_self.agent_name, thread_id
                )
                return None

            def after_agent(middleware_self, state, runtime: Runtime):
                thread_id = runtime.context.get("thread_id", "unknown") if runtime.context else "unknown"
                logger.info(
                    "[AgentRuntime] After agent | id=%s name=%s thread=%s",
                    middleware_self.agent_id, middleware_self.agent_name, thread_id
                )
                return None

        middlewares.append(LoggingMiddleware())
        return middlewares

    def _get_state_schema(self, agent_config: AgentConfig) -> type:
        """获取状态 Schema"""
        class AgentState(TypedDict, total=False):
            messages: Annotated[List[BaseMessage], add_messages]
            context: Annotated[Dict[str, Any], lambda a, b: {**a, **b}]
            metadata: Dict[str, Any]
            plan: NotRequired[List[str]]
            todo_list: NotRequired[List[Dict[str, Any]]]
            subagent_results: NotRequired[Dict[str, Any]]
        return AgentState

    async def _create_task_tool(self, parent_config: AgentConfig) -> Callable:
        """创建 task 工具用于多 Agent 场景"""
        from langchain_core.tools import tool

        @tool
        async def delegate_to_subagent(
            task_description: str,
            subagent_type: str,
            expected_output: str,
        ) -> str:
            """Delegate a task to a specialized subagent."""
            logger.info(
                "[TaskTool] Delegating task | type=%s parent=%s",
                subagent_type, parent_config.name
            )

            try:
                subagent_config = await self._get_subagent_config(parent_config.id, subagent_type)
                if not subagent_config:
                    return f"[ERROR] Subagent '{subagent_type}' not found"

                subagent = await self.create_agent(subagent_config)
                result = await subagent.ainvoke({
                    "messages": [HumanMessage(content=f"{task_description}\n\nExpected output: {expected_output}")]
                })

                return self._extract_response(result)

            except Exception as e:
                logger.exception("[TaskTool] Subagent execution failed")
                return f"[ERROR] Subagent failed: {str(e)}"

        return delegate_to_subagent

    async def _get_subagent_config(self, parent_id: str, subagent_type: str) -> Optional[AgentConfig]:
        """获取子 Agent 配置"""
        if parent_id in self._subagent_cache:
            return self._subagent_cache[parent_id].get(subagent_type)

        result = await self.db.execute(select(AgentConfig).where(AgentConfig.user_id == 1))
        configs = result.scalars().all()

        self._subagent_cache[parent_id] = {cfg.name: cfg for cfg in configs}
        return self._subagent_cache[parent_id].get(subagent_type)

    def _extract_response(self, result: dict) -> str:
        """从执行结果中提取响应"""
        messages = result.get("messages", [])
        if not messages:
            return ""

        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict) and "text" in block:
                            text_parts.append(block["text"])
                    return "\n".join(text_parts)
        return ""


# ============================================================
# 多 Agent 编排器
# ============================================================

class BaseOrchestrator(ABC):
    """编排器基类"""

    def __init__(self, db: AsyncSession, model_gateway: Any, skill_registry: Any, multi_config: dict):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.multi_config = multi_config
        self.workers = multi_config.get("workers", [])

    @abstractmethod
    async def execute(self, user_id: int, query: str, session_id: Optional[str] = None) -> dict:
        """执行编排"""
        pass

    async def _get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
        return result.scalar_one_or_none()

    async def _execute_subagent(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
    ) -> dict:
        """执行子 Agent"""
        agent_config = await self._get_agent_config(agent_id)
        if not agent_config:
            return {"error": f"Agent not found: {agent_id}"}

        factory = AgentFactory(self.db, self.model_gateway, self.skill_registry)
        try:
            result = await factory.execute(
                agent_id=agent_id,
                user_id=user_id,
                query=query,
                runtime_config={},
            )
            return result
        except Exception as e:
            logger.error(f"[SubAgent] Execution failed: {e}")
            return {"error": str(e)}


class SupervisorOrchestrator(BaseOrchestrator):
    """Supervisor 模式编排器"""

    async def execute(self, user_id: int, query: str, session_id: Optional[str] = None) -> dict:
        run_id = str(uuid4())
        logger.info("[Supervisor] Starting orchestration | run=%s workers=%d", run_id, len(self.workers))

        results = {}
        for i, worker in enumerate(self.workers):
            worker_id = worker.get("agent_id")
            model_config = ModelConfig(**worker["model_config"]) if worker.get("model_config") else None

            result = await self._execute_subagent(worker_id, user_id, query, model_config)
            results[worker_id] = result

        return {
            "run_id": run_id,
            "mode": "supervisor",
            "agent_results": results,
            "final_response": self._aggregate_results(results),
        }

    def _aggregate_results(self, results: dict) -> str:
        if not results:
            return "No results from workers."

        responses = []
        for worker_id, result in results.items():
            if "error" in result:
                responses.append(f"[{worker_id}] Error: {result['error']}")
            else:
                responses.append(f"[{worker_id}] {result.get('response', '')}")

        return "\n\n".join(responses)


class RoundRobinOrchestrator(BaseOrchestrator):
    """轮询模式编排器"""

    async def execute(self, user_id: int, query: str, session_id: Optional[str] = None) -> dict:
        run_id = str(uuid4())
        logger.info("[RoundRobin] Starting orchestration | run=%s workers=%d", run_id, len(self.workers))

        results = {}
        current_query = query

        for i, worker in enumerate(self.workers):
            worker_id = worker.get("agent_id")
            model_config = ModelConfig(**worker["model_config"]) if worker.get("model_config") else None

            result = await self._execute_subagent(worker_id, user_id, current_query, model_config)
            results[worker_id] = result

            if "response" in result:
                current_query = f"{query}\n\nPrevious result:\n{result['response']}"

        return {
            "run_id": run_id,
            "mode": "round_robin",
            "agent_results": results,
            "final_response": self._aggregate_results(results),
        }

    def _aggregate_results(self, results: dict) -> str:
        if not results:
            return "No results from workers."

        responses = [r.get("response", "") for r in results.values() if "error" not in r]
        return "\n\n---\n\n".join(responses)


class VotingOrchestrator(BaseOrchestrator):
    """投票模式编排器"""

    async def execute(self, user_id: int, query: str, session_id: Optional[str] = None) -> dict:
        run_id = str(uuid4())
        logger.info("[Voting] Starting orchestration | run=%s workers=%d", run_id, len(self.workers))

        tasks = []
        for worker in self.workers:
            worker_id = worker.get("agent_id")
            model_config = ModelConfig(**worker["model_config"]) if worker.get("model_config") else None
            tasks.append(self._execute_subagent(worker_id, user_id, query, model_config))

        worker_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for i, worker in enumerate(self.workers):
            result = worker_results[i]
            if isinstance(result, Exception):
                results[worker.get("agent_id")] = {"error": str(result)}
            else:
                results[worker.get("agent_id")] = result

        return {
            "run_id": run_id,
            "mode": "voting",
            "agent_results": results,
            "final_response": self._vote_for_best(results),
        }

    def _vote_for_best(self, results: dict) -> str:
        for result in results.values():
            if "error" not in result and "response" in result:
                return result["response"]
        return "All workers failed to provide a valid response."


# ============================================================
# Meta Agent 系统
# ============================================================

META_AGENT_SYSTEM_PROMPT = """你是一个智能体创建和管理助手 (Meta Agent)，拥有自主决策能力。

## 你的能力
1. **创建智能体** - 当用户需要新类型的智能体时，调用 `create_agent` 工具
2. **执行智能体** - 当现有智能体可以完成任务时，调用 `execute_agent` 工具
3. **查询智能体** - 当需要了解现有智能体时，调用 `list_agents` 工具
4. **知识库管理** - 你可以使用以下 MCP 工具管理知识库：
   - `create_knowledge_base(name, description, ...)` - 创建知识库
   - `list_knowledge_bases(search, limit, offset)` - 查询知识库列表
   - `get_knowledge_base(kb_id)` - 获取知识库详情
   - `update_knowledge_base(kb_id, name, description, ...)` - 更新知识库
   - `delete_knowledge_base(kb_id)` - 删除知识库
   - `search_knowledge_base(query, kb_ids, top_k)` - 搜索知识库内容

## 你的工作流程
1. 分析用户需求
2. 决策：创建新智能体 or 使用现有智能体 or 直接调用 MCP 工具
3. 多智能体协作时，整合结果返回

## 可用工具
- `create_agent(name, system_prompt, description, agent_type, enabled_skills)` - 创建新智能体
- `execute_agent(agent_id, query, kb_ids, top_k, enable_rerank, model_name)` - 执行现有智能体
- `list_agents(status)` - 查询现有智能体列表
- MCP 工具：知识库管理、模型管理、提示词管理、Agent Hub 相关工具
"""


class MetaAgentFactory:
    """Meta Agent 工厂"""

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

    async def _create_llm(self) -> Any:
        """创建 Meta Agent 使用的 LLM"""
        from app.services.model_gateway_service import ModelGatewayService
        from app.services.agent_runtime_service import create_langchain_llm

        model_gateway = ModelGatewayService(self.db)
        model_config = None

        if self.model_name:
            model_config = await model_gateway.get_model_by_name(self.model_name)
            if not model_config:
                logger.warning("Model '%s' not found, using default", self.model_name)

        if not model_config:
            from app.schemas.chat import ModelConfig
            model_config = ModelConfig(
                provider="qwen3.5-397b",
                model="qwen3.5-397b-a17b",
                temperature=0.7,
                max_tokens=4096,
            )

        return await create_langchain_llm(model_config, self.db)

    async def _get_tools(self) -> list:
        """获取 Meta Agent 使用的工具 - 通过 MCP Client 调用 MCP Server"""
        from app.tools.meta_agent_tools import (
            create_create_agent_tool,
            create_execute_agent_tool,
            create_list_agents_tool,
        )

        tools = [
            # 基础工具
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

        # 通过 MCP Client 加载 MCP Server 的工具
        try:
            from app.mcp_integration.client import MCPClient

            async with MCPClient(self.db) as client:
                mcp_tools = await client.get_all_langchain_tools()
                tools.extend(mcp_tools)

            logger.info("[MetaAgent] Loaded %d tools (including %d MCP tools)", len(tools), len(mcp_tools))
        except Exception as e:
            logger.warning("[MetaAgent] Failed to load MCP tools: %s", e)

        return tools

    async def create_meta_agent(self) -> Any:
        """创建 Meta Agent"""
        from langchain.agents import create_agent
        from app.tools.meta_agent_tools import (
            create_create_agent_tool,
            create_execute_agent_tool,
            create_list_agents_tool,
        )
        from app.services.model_gateway_service import ModelGatewayService
        from app.services.agent_runtime_service import create_langchain_llm
        from app.mcp_integration.client import MCPClient

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

        # 通过 MCP Client 加载 MCP 工具
        try:
            async with MCPClient(self.db) as client:
                mcp_tools = await client.get_all_langchain_tools()
                tools.extend(mcp_tools)
                logger.info("[MetaAgent] Loaded %d MCP tools", len(mcp_tools))
        except Exception as e:
            logger.warning("[MetaAgent] Failed to load MCP tools: %s", e)

        # 使用传入的 model_name 从数据库获取模型配置
        model_gateway = ModelGatewayService(self.db)
        model_config = None
        if self.model_name:
            model_config = await model_gateway.get_model_by_name(self.model_name)
            if not model_config:
                logger.warning("Model '%s' not found, using default", self.model_name)

        # 回退到默认配置
        if not model_config:
            model_config = ModelConfig(
                provider="qwen3.5-397b",
                model="qwen3.5-397b-a17b",
                temperature=0.7,
                max_tokens=4096,
            )

        llm = await create_langchain_llm(model_config, self.db)
        llm_with_tools = llm.bind_tools(tools)

        class MetaAgentState(TypedDict):
            messages: Annotated[List[BaseMessage], add_messages]
            context: Dict[str, Any]
            created_agents: List[str]
            agents_used: List[str]

        agent = create_agent(
            model=llm_with_tools,
            tools=tools,
            system_prompt=META_AGENT_SYSTEM_PROMPT,
            state_schema=MetaAgentState,
        )

        logger.info("[MetaAgentFactory] Meta Agent created with tools: %s", [t.name for t in tools])
        return agent


# ============================================================
# Agent Service - 统一服务层
# ============================================================

class AgentService:
    """
    统一的智能体服务层

    支持三种执行模式：
    1. SINGLE - 单个智能体执行
    2. MULTI - 多智能体协作
    3. META - Meta Agent 自主决策
    """

    def __init__(self, db: AsyncSession, model_gateway: Any, skill_registry: Any):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry

        # 核心组件
        self.agent_factory = AgentFactory(db, model_gateway, skill_registry)
        self.graph_builder = StateGraphBuilder(model_gateway, skill_registry, db)

    async def execute(self, request: AgentExecuteRequest) -> AgentExecuteResult:
        """
        执行智能体 - 统一入口

        Args:
            request: 执行请求

        Returns:
            执行结果
        """
        start_time = time.time()
        run_id = str(uuid4())

        logger.info(
            "[AgentService] Starting execution | run=%s mode=%s agent=%s user=%s",
            run_id, request.execution_mode, request.agent_id, request.user_id
        )

        # 根据执行模式选择执行路径
        if request.execution_mode == ExecutionMode.META:
            result = await self._execute_meta(request, run_id)
        elif request.execution_mode in [ExecutionMode.MULTI, ExecutionMode.SUPERVISOR, ExecutionMode.ROUND_ROBIN, ExecutionMode.VOTING]:
            result = await self._execute_multi(request, run_id)
        else:  # SINGLE
            result = await self._execute_single(request, run_id)

        # 记录调用日志
        await self._log_execution(request, result, run_id, start_time)

        return result

    async def execute_stream(self, request: AgentExecuteRequest) -> AsyncGenerator[str, None]:
        """流式执行智能体"""
        run_id = str(uuid4())
        start_time = time.time()

        logger.info(
            "[AgentService] Starting stream execution | run=%s mode=%s agent=%s user=%s",
            run_id, request.execution_mode, request.agent_id, request.user_id
        )

        try:
            if request.execution_mode == ExecutionMode.META:
                async for chunk in self._execute_meta_stream(request, run_id):
                    yield chunk
            elif request.execution_mode in [ExecutionMode.MULTI, ExecutionMode.SUPERVISOR, ExecutionMode.ROUND_ROBIN, ExecutionMode.VOTING]:
                async for chunk in self._execute_multi_stream(request, run_id):
                    yield chunk
            else:
                async for chunk in self._execute_single_stream(request, run_id):
                    yield chunk

            # 发送完成事件
            latency_ms = int((time.time() - start_time) * 1000)
            yield json.dumps({
                "type": "complete",
                "node": "system",
                "event": "complete",
                "data": {"run_id": run_id, "latency_ms": latency_ms}
            }, ensure_ascii=False)

        except Exception as e:
            logger.exception("[AgentService] Stream execution failed | run=%s", run_id)
            yield json.dumps({
                "type": "error",
                "node": "system",
                "event": "error",
                "data": {"error": str(e)}
            }, ensure_ascii=False)

    # ============================================================
    # 单智能体执行
    # ============================================================

    async def _execute_single(self, request: AgentExecuteRequest, run_id: str) -> AgentExecuteResult:
        """执行单个智能体"""
        # 获取 Agent 配置
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == request.agent_id))
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {request.agent_id}")

        thread_id = f"{request.user_id}:{request.agent_id}:{request.session_id or 'default'}"

        # 获取对话历史
        memory_service = AgentMemoryService(self.db)
        history = await memory_service.get_conversation(request.agent_id, request.user_id, thread_id)

        # 创建运行时配置
        runtime_config = {
            "kb_ids": request.kb_ids,
            "top_k": request.top_k,
            "enable_rerank": request.enable_rerank,
            "model_name": request.model_name,
            "run_id": run_id,
            **request.runtime_config,
        }

        # 使用工厂创建并执行 Agent
        agent = await self.agent_factory.create_agent(agent_config, runtime_config)

        sync_db = sync_session_factory()
        try:
            checkpoint_saver = DatabaseCheckpointSaver(sync_db)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_saver": checkpoint_saver,
                    "runtime_config": runtime_config,
                }
            }

            response = await agent.ainvoke({
                "messages": history + [HumanMessage(content=request.query)],
                "context": {},
            }, config=config)

            messages = response.get("messages", [])
            response_text = ""
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content:
                    response_text = str(msg.content)
                    break

            result = AgentExecuteResult(
                run_id=run_id,
                agent_id=request.agent_id,
                response=response_text,
                messages=messages,
                agents_used=[],
            )

            # 保存会话到 conversations 表
            await self._save_conversation(request, response_text)

            return result
        finally:
            sync_db.close()

    async def _execute_single_stream(self, request: AgentExecuteRequest, run_id: str) -> AsyncGenerator[str, None]:
        """流式执行单个智能体"""
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == request.agent_id))
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {request.agent_id}")

        thread_id = f"{request.user_id}:{request.agent_id}:{request.session_id or 'default'}"

        memory_service = AgentMemoryService(self.db)
        history = await memory_service.get_conversation(request.agent_id, request.user_id, thread_id)

        runtime_config = {
            "kb_ids": request.kb_ids,
            "top_k": request.top_k,
            "enable_rerank": request.enable_rerank,
            "model_name": request.model_name,
            "run_id": run_id,
            **request.runtime_config,
        }

        agent = await self.agent_factory.create_agent(agent_config, runtime_config)

        sync_db = sync_session_factory()
        try:
            checkpoint_saver = DatabaseCheckpointSaver(sync_db)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_saver": checkpoint_saver,
                    "runtime_config": runtime_config,
                }
            }

            last_content = ""
            async for event, metadata in agent.astream(
                {
                    "messages": history + [HumanMessage(content=request.query)],
                    "context": {},
                },
                config=config,
                stream_mode="messages",
            ):
                if hasattr(event, 'type') and event.type == 'tool':
                    continue

                content = ""
                if hasattr(event, 'content'):
                    content = event.content if event.content else ""

                if content:
                    if isinstance(content, str) and content.startswith(last_content):
                        new_content = content[len(last_content):]
                        if new_content:
                            # 返回 JSON 格式
                            yield json.dumps({
                                "type": "token",
                                "content": new_content,
                            }, ensure_ascii=False)
                            last_content = content
                    else:
                        # 返回 JSON 格式
                        yield json.dumps({
                            "type": "token",
                            "content": content,
                        }, ensure_ascii=False)
                        last_content = content
        finally:
            sync_db.close()

    # ============================================================
    # 多智能体执行
    # ============================================================

    async def _execute_multi(self, request: AgentExecuteRequest, run_id: str) -> AgentExecuteResult:
        """执行多智能体协作"""
        # 获取 Agent 配置
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == request.agent_id))
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {request.agent_id}")

        multi_config = agent_config.multi_agent_config or {}
        mode = multi_config.get("mode", "round_robin")

        # 创建对应的编排器
        orchestrator = self._create_orchestrator(mode, multi_config)
        if not orchestrator:
            raise ValueError(f"Unknown orchestration mode: {mode}")

        exec_result = await orchestrator.execute(request.user_id, request.query, request.session_id)

        result = AgentExecuteResult(
            run_id=run_id,
            agent_id=request.agent_id,
            response=exec_result.get("final_response", ""),
            messages=[],
            agents_used=list(exec_result.get("agent_results", {}).keys()),
            metadata=exec_result,
        )

        # 保存会话到 conversations 表
        await self._save_conversation(request, result.response)

        return result

    async def _execute_multi_stream(self, request: AgentExecuteRequest, run_id: str) -> AsyncGenerator[str, None]:
        """流式执行多智能体协作"""
        # 简化实现：非流式执行后返回
        result = await self._execute_multi(request, run_id)
        # 返回 JSON 格式
        yield json.dumps({
            "type": "token",
            "content": result.response,
        }, ensure_ascii=False)

    def _create_orchestrator(self, mode: str, multi_config: dict) -> Optional[BaseOrchestrator]:
        """创建对应的编排器"""
        if mode == "supervisor":
            return SupervisorOrchestrator(self.db, self.model_gateway, self.skill_registry, multi_config)
        elif mode == "round_robin":
            return RoundRobinOrchestrator(self.db, self.model_gateway, self.skill_registry, multi_config)
        elif mode == "voting":
            return VotingOrchestrator(self.db, self.model_gateway, self.skill_registry, multi_config)
        return None

    # ============================================================
    # Meta Agent 执行
    # ============================================================

    async def _execute_meta(self, request: AgentExecuteRequest, run_id: str) -> AgentExecuteResult:
        """执行 Meta Agent"""
        from langchain_core.messages import AIMessage
        from app.services.agent_memory_service import AgentMemoryService

        factory = MetaAgentFactory(
            self.db,
            request.user_id,
            request.tenant_id,
            kb_ids=request.kb_ids,
            top_k=request.top_k,
            enable_rerank=request.enable_rerank,
            model_name=request.model_name,
        )

        meta_agent = await factory.create_meta_agent()

        result = await meta_agent.ainvoke({
            "messages": [HumanMessage(content=request.query)]
        })

        messages = result.get("messages", [])
        response_text = ""
        for msg in reversed(messages):
            if hasattr(msg, 'content') and msg.content:
                response_text = str(msg.content)
                break

        # 保存对话历史到 agent_memories (运行时记忆)
        try:
            memory_service = AgentMemoryService(self.db)
            thread_id = f"{request.user_id}:meta:{request.session_id or 'default'}"
            await memory_service.add_conversation(
                agent_id="00000000-0000-0000-0000-000000000001",
                user_id=request.user_id,
                thread_id=thread_id,
                messages=[request.query, response_text],
                ttl_hours=24
            )
        except Exception as e:
            logger.warning("[MetaAgent] Failed to save to agent_memories: %s", e)

        # 保存对话历史到 conversations 表 (用户可见的会话)
        await self._save_conversation(request, response_text)

        return AgentExecuteResult(
            run_id=run_id,
            agent_id=None,
            response=response_text,
            messages=messages,
            agents_used=result.get("agents_used", []),
        )

    async def _execute_meta_stream(self, request: AgentExecuteRequest, run_id: str) -> AsyncGenerator[str, None]:
        """流式执行 Meta Agent - 返回完整执行链路轨迹"""
        from langchain_core.messages import AIMessageChunk, HumanMessage
        from langchain.agents import create_agent
        from app.services.agent_memory_service import AgentMemoryService

        factory = MetaAgentFactory(
            self.db,
            request.user_id,
            request.tenant_id,
            kb_ids=request.kb_ids,
            top_k=request.top_k,
            enable_rerank=request.enable_rerank,
            model_name=request.model_name,
        )

        # 获取 LLM 和工具
        llm = await factory._create_llm()
        tools = await factory._get_tools()

        # 创建 Agent
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=META_AGENT_SYSTEM_PROMPT,
        )

        # 发送 Meta Agent 节点开始事件
        yield json.dumps({
            "type": "node_start",
            "node": "meta_agent",
            "run_id": run_id,
            "metadata": {"model": factory.model_name},
        }, ensure_ascii=False)

        # 使用 ainvoke 执行 Agent，然后流式输出 LLM 响应
        messages = [HumanMessage(content=f"{request.query}")]
        accumulated_response = ""

        try:
            # 先执行 Agent 获取完整响应
            response = await agent.ainvoke({"messages": messages})
            response_messages = response.get("messages", [])

            if response_messages:
                last_msg = response_messages[-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    full_content = str(last_msg.content)

                    # 将完整内容分段发送，模拟流式效果
                    # 按字符分组发送（每 3 个字符一批）
                    chunk_size = 3
                    for i in range(0, len(full_content), chunk_size):
                        chunk = full_content[i:i+chunk_size]
                        accumulated_response += chunk
                        yield json.dumps({
                            "type": "token",
                            "node": "model",
                            "content": chunk,
                        }, ensure_ascii=False)
                        # 添加小延迟模拟真实流式
                        await asyncio.sleep(0.01)

            # 保存对话历史到 agent_memories (运行时记忆)
            try:
                memory_service = AgentMemoryService(self.db)
                thread_id = f"{request.user_id}:meta:{request.session_id or 'default'}"
                await memory_service.add_conversation(
                    agent_id="00000000-0000-0000-0000-000000000001",
                    user_id=request.user_id,
                    thread_id=thread_id,
                    messages=[request.query, accumulated_response],
                    ttl_hours=24
                )
            except Exception as e:
                logger.warning("[MetaAgent] Failed to save to agent_memories: %s", e)

            # 保存对话历史到 conversations 表 (用户可见的会话)
            # 创建临时 request 对象用于 _save_conversation
            stream_request = AgentExecuteRequest(
                query=request.query,
                user_id=request.user_id,
                tenant_id=request.tenant_id,
                agent_id=None,
                kb_ids=request.kb_ids,
                top_k=request.top_k,
                enable_rerank=request.enable_rerank,
                model_name=request.model_name,
                session_id=request.session_id,
                debug_mode=request.debug_mode,
                execution_mode=ExecutionMode.META,
                runtime_config=request.runtime_config,
            )
            await self._save_conversation(stream_request, accumulated_response)

        except Exception as e:
            logger.error(f"Meta Agent stream error: {e}")
            yield json.dumps({
                "type": "error",
                "node": "meta_agent",
                "error": str(e),
            }, ensure_ascii=False)

        # 发送 Meta Agent 节点结束事件
        yield json.dumps({
            "type": "node_end",
            "node": "meta_agent",
            "run_id": run_id,
        }, ensure_ascii=False)

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _save_conversation(
        self,
        request: AgentExecuteRequest,
        response: str,
    ) -> None:
        """保存会话到 conversations 表"""
        try:
            from app.services.conversation_service import create_or_update_conversation_from_agent

            session_id = request.session_id or str(uuid4())
            messages = [
                {"role": "user", "content": request.query},
                {"role": "assistant", "content": response},
            ]

            await create_or_update_conversation_from_agent(
                db=self.db,
                user_id=request.user_id,
                session_id=session_id,
                agent_id=request.agent_id,
                title=request.query[:50],
                messages=messages,
                kb_ids=request.kb_ids,
            )

            logger.info(
                "[AgentService] Conversation saved | user=%s session=%s",
                request.user_id, session_id
            )
        except Exception as e:
            logger.warning("[AgentService] Failed to save conversation: %s", e)

    async def _log_execution(
        self,
        request: AgentExecuteRequest,
        result: AgentExecuteResult,
        run_id: str,
        start_time: float,
    ) -> None:
        """记录执行日志"""
        try:
            latency_ms = int((time.time() - start_time) * 1000)

            # Meta Agent 模式没有固定的 agent_id，使用特殊值
            agent_id = result.agent_id or "00000000-0000-0000-0000-000000000000"

            call_log = AgentCallLog(
                agent_id=agent_id,
                run_id=run_id,
                user_id=request.user_id,
                thread_id=f"{request.user_id}:{request.agent_id or 'meta'}:{request.session_id or 'default'}",
                input_summary={"query": request.query[:500] if request.query else ""},
                output_summary={"response": result.response[:500] if result.response else ""},
                latency_ms=latency_ms,
                status="success",
            )

            self.db.add(call_log)
            await self.db.commit()

            logger.info(
                "[AgentService] Execution logged | run=%s agent=%s latency=%dms",
                run_id, result.agent_id, latency_ms
            )
        except Exception as e:
            logger.warning("[AgentService] Failed to log execution | run=%s error=%s", run_id, e)


# ============================================================
# 便捷函数
# ============================================================

async def create_agent_service(
    db: AsyncSession,
    model_gateway: Any,
    skill_registry: Any,
) -> AgentService:
    """创建 AgentService 实例"""
    return AgentService(db, model_gateway, skill_registry)
