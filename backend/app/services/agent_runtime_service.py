"""
Agent Runtime 服务
基于 LangGraph 实现 Agent 的动态加载和运行

v2.0: 整合 AgentGraphFactory，支持 LangGraph 工厂函数模式
- 运行时动态构建图
- 支持 MCP 工具动态加载
- 支持技能渐进式加载
- 支持中间件链
"""
import time
from typing import Optional, AsyncGenerator, Any
from datetime import datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import AgentConfig, AgentCallLog
from app.services.agent_checkpoint_service import DatabaseCheckpointSaver
from app.services.agent_memory_service import AgentMemoryService
from app.services.agent_graph_factory import StateGraphBuilder, WorkflowState as AgentState
from app.schemas.chat import ModelConfig
from app.core.database import engine, async_session_factory
from sqlalchemy.orm import sessionmaker

# 同步 Session factory 用于 LangGraph CheckpointSaver
sync_session_factory = sessionmaker(bind=engine.sync_engine)

def get_sync_db():
    """获取同步数据库 Session"""
    db = sync_session_factory()
    try:
        yield db
    finally:
        db.close()


async def create_langchain_llm(model_config: Any, db: Any = None) -> Any:
    """
    根据模型配置创建 LangChain LLM 实例

    支持主流 LLM 供应商，URL 和 API Key 统一从供应商配置获取

    注意：model_config 可能是：
    1. ModelConfig schema (使用 model, base_url 字段)
    2. ModelConfig ORM 模型 (使用 model_id, api_url 字段)
    """
    from sqlalchemy import select
    from app.models.model_config import ModelConfig as DBModelConfig
    from app.models.model_gateway import ModelProvider

    # 兼容 schema 和 ORM 模型的字段名差异
    # schema: model, base_url | ORM: model_id, api_url
    model_name = getattr(model_config, 'model', None) or getattr(model_config, 'model_id', None)
    provider_code = getattr(model_config, 'provider', '').lower()
    temperature = getattr(model_config, 'temperature', 0.7)
    max_tokens = getattr(model_config, 'max_tokens', 4096)
    top_p = getattr(model_config, 'top_p', 1.0)

    # 统一从供应商配置获取 URL 和 API Key
    api_key = None
    api_url = None

    if db and provider_code:
        try:
            # 从 ModelProvider 获取供应商配置
            result = await db.execute(
                select(ModelProvider).where(
                    ModelProvider.code == provider_code,
                ).limit(1)
            )
            provider_config = result.scalar_one_or_none()
            if provider_config:
                api_url = provider_config.base_url
                api_key = provider_config.api_key
                print(f"[LLM] 使用供应商配置 | provider={provider_code} url={api_url}")
        except Exception as e:
            print(f"Failed to get provider config: {e}")

    if provider_code == "anthropic":
        from langchain_anthropic import ChatAnthropic
        from app.config import settings
        import os
        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            anthropic_api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", settings.secret_key),
        )

    elif provider_code == "openai":
        from langchain_openai import ChatOpenAI
        import os
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            base_url=api_url if api_url else None,
        )

    elif provider_code == "azure":
        from langchain_openai import AzureChatOpenAI
        import os
        return AzureChatOpenAI(
            azure_deployment=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            api_key=api_key or os.environ.get("AZURE_OPENAI_API_KEY", ""),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )

    elif provider_code == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        import os
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            google_api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
        )

    elif provider_code == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            num_predict=max_tokens,
            top_p=top_p,
            base_url=api_url or "http://localhost:11434",
        )

    elif provider_code == "local_qwen":
        # 本地 Qwen 模型，使用 OpenAI 兼容接口
        from langchain_openai import ChatOpenAI

        # 确保 api_url 不以 /v1 结尾，避免重复
        if api_url:
            api_url = api_url.rstrip("/")
            if api_url.endswith("/v1"):
                api_url = api_url[:-3]
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            base_url=f"{api_url}/v1" if api_url else None,
            api_key=api_key or "not-needed",
        )

    else:
        # 默认使用 OpenAI 兼容接口
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            base_url=f"{api_url}/v1" if api_url else None,
            api_key=api_key or "not-needed",
        )


class AgentState(TypedDict):
    """Agent 运行状态"""
    messages: list
    context: dict
    current_step: str
    metadata: dict


class AgentRuntime:
    """
    Agent 运行时服务

    核心特性：
    1. 动态加载 Agent 配置（从数据库）
    2. 运行时由用户选择模型
    3. 支持单智能体和多智能体编排
    4. 用户隔离（通过 thread_id）
    5. 记忆持久化
    6. v2.0: 基于 StateGraphBuilder 的工厂函数模式
    """

    def __init__(
        self,
        db: AsyncSession,
        model_gateway_service: Any,
        skill_registry: Any,
        use_factory_mode: bool = False,
    ):
        self.db = db
        self.model_gateway = model_gateway_service
        self.skill_registry = skill_registry
        self.graph_cache: dict[str, Any] = {}  # agent_id -> compiled graph

        # v2.0: 工厂模式支持
        self.use_factory_mode = use_factory_mode
        if use_factory_mode:
            self.graph_factory = StateGraphBuilder(
                model_gateway_service=model_gateway_service,
                skill_registry=skill_registry,
                db=db,
            )
        else:
            self.graph_factory = None

    async def _create_llm(self, model_config: ModelConfig) -> Any:
        """根据模型配置创建 LLM 实例"""
        return await create_langchain_llm(model_config, self.db)

    def _load_tools(self, enabled_skills: list[str]) -> list:
        """加载启用的 Skill 工具"""
        tools = []
        for skill_id in enabled_skills:
            tool = self.skill_registry.get_tool(skill_id)
            if tool:
                tools.append(tool)
        return tools

    async def _build_single_agent_graph(
        self,
        agent_config: AgentConfig,
        model_config: ModelConfig,
    ) -> StateGraph:
        """构建单智能体图"""
        llm = await self._create_llm(model_config)
        tools = self._load_tools(agent_config.enabled_skills or [])

        if tools:
            llm = llm.bind_tools(tools)

        def agent_node(state: AgentState):
            """Agent 节点：处理用户输入并生成响应"""
            messages = state["messages"]

            if messages and not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=agent_config.system_prompt)] + messages
            elif not messages:
                messages = [SystemMessage(content=agent_config.system_prompt)]

            response = llm.invoke(messages)
            return {"messages": messages + [response]}

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)

        return graph

    async def _build_multi_agent_graph(
        self,
        agent_config: AgentConfig,
        model_config: ModelConfig,
    ) -> StateGraph:
        """构建多智能体编排图"""
        multi_config = agent_config.multi_agent_config or {}
        workers = multi_config.get("workers", [])

        llm = await self._create_llm(model_config)

        def supervisor_node(state: AgentState):
            """Supervisor 节点：决定下一步执行哪个 worker"""
            messages = state["messages"]
            context = state.get("context", {})

            current_idx = context.get("current_worker_idx", 0)
            if current_idx >= len(workers):
                return {"current_step": "FINISH", "context": context}

            worker = workers[current_idx]
            context["current_worker_idx"] = current_idx + 1
            context["next"] = worker.get("agent_id", "agent")

            return {"current_step": "working", "context": context}

        def worker_node(state: AgentState, worker_info: dict):
            """Worker 节点：执行具体任务"""
            role = worker_info.get("role", "assistant")

            system_msg = SystemMessage(content=f"{role}: {agent_config.system_prompt}")
            messages = [system_msg] + state["messages"]
            response = llm.invoke(messages)

            return {"messages": state["messages"] + [response]}

        graph = StateGraph(AgentState)
        graph.add_node("supervisor", supervisor_node)

        for worker in workers:
            worker_id = worker.get("agent_id", "unknown")
            graph.add_node(
                f"worker_{worker_id}",
                lambda s, w=worker: worker_node(s, w)
            )
            graph.add_edge(f"worker_{worker_id}", "supervisor")

        graph.add_edge(START, "supervisor")

        return graph

    async def _get_or_build_graph(
        self,
        agent_id: str,
        model_config: ModelConfig,
        force_rebuild: bool = False,
        runtime_config: Optional[dict] = None,
    ) -> Any:
        """
        获取或构建 Agent 图

        v2.0: 支持工厂模式动态构建
        """
        # 工厂模式：每次动态构建
        if self.use_factory_mode and self.graph_factory:
            run_id = str(uuid4())
            return await self.graph_factory.build_graph_for_run(
                agent_id=agent_id,
                user_id=0,  # 从 runtime_config 获取
                runtime_config=runtime_config or {},
                run_id=run_id,
            )

        # 传统模式：缓存图
        cache_key = f"{agent_id}:{model_config.provider}:{model_config.model}"

        if not force_rebuild and cache_key in self.graph_cache:
            return self.graph_cache[cache_key]

        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {agent_id}")

        if agent_config.agent_type == "multi":
            graph = await self._build_multi_agent_graph(agent_config, model_config)
        else:
            graph = await self._build_single_agent_graph(agent_config, model_config)

        compiled = graph.compile()
        self.graph_cache[cache_key] = compiled
        return compiled

    async def run(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        session_id: Optional[str] = None,
    ) -> dict:
        """运行 Agent"""
        start_time = time.time()
        run_id = str(uuid4())
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        graph = await self._get_or_build_graph(agent_id, model_config)

        human_message = HumanMessage(content=query)

        # 创建同步 Session 用于 CheckpointSaver (LangGraph 需要同步 Session)
        sync_db = sync_session_factory()
        try:
            checkpoint_saver = DatabaseCheckpointSaver(sync_db)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_saver": checkpoint_saver,
                }
            }

            memory_service = AgentMemoryService(self.db)
            history = await memory_service.get_conversation(agent_id, user_id, thread_id)

            initial_state = {
                "messages": history + [human_message],
                "context": {},
                "current_step": "start",
                "metadata": {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                }
            }

            try:
                result = await graph.ainvoke(initial_state, config=config)

                messages = result.get("messages", [])
                response = messages[-1].content if messages else ""

                await memory_service.add_conversation(
                    agent_id, user_id, thread_id,
                    [query, response],
                    ttl_hours=24
                )

                await self._log_call(
                    agent_id, user_id, thread_id, run_id,
                    model_config, "success",
                    input_tokens=0, output_tokens=0,
                    latency_ms=int((time.time() - start_time) * 1000)
                )

                return {
                    "run_id": run_id,
                    "response": response,
                    "messages": messages,
                }

            except Exception as e:
                await self._log_call(
                    agent_id, user_id, thread_id, run_id,
                    model_config, "error",
                    error_message=str(e)
                )
                raise
        finally:
            sync_db.close()

    async def run_stream(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式运行 Agent"""
        run_id = str(uuid4())
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        graph = await self._get_or_build_graph(agent_id, model_config)

        human_message = HumanMessage(content=query)

        # 创建同步 Session 用于 CheckpointSaver
        sync_db = sync_session_factory()
        try:
            checkpoint_saver = DatabaseCheckpointSaver(sync_db)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_saver": checkpoint_saver,
                }
            }

            memory_service = AgentMemoryService(self.db)
            history = await memory_service.get_conversation(agent_id, user_id, thread_id)

            initial_state = {
                "messages": history + [human_message],
                "context": {},
                "current_step": "start",
                "metadata": {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                }
            }

            full_response = []
            try:
                async for event, metadata in graph.astream(
                    initial_state,
                    config=config,
                    stream_mode="messages",
                ):
                    if hasattr(event, 'content') and event.content:
                        yield event.content
                        full_response.append(event.content)

                if full_response:
                    await memory_service.add_conversation(
                        agent_id, user_id, thread_id,
                        [query, "".join(full_response)],
                        ttl_hours=24
                    )

            except Exception as e:
                yield f"[ERROR] {str(e)}"
        finally:
            sync_db.close()

    async def _log_call(
        self,
        agent_id: str,
        user_id: int,
        thread_id: str,
        run_id: str,
        model_config: ModelConfig,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        error_message: Optional[str] = None,
    ):
        """记录调用日志"""
        log = AgentCallLog(
            id=str(uuid4()),
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            run_id=run_id,
            model_provider=model_config.provider,
            model_name=model_config.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.commit()

        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent:
            agent.total_runs += 1
            agent.total_tokens += input_tokens + output_tokens
            await self.db.commit()

    async def clear_memory(self, agent_id: str, user_id: int, session_id: str) -> bool:
        """清除指定会话的记忆"""
        memory_service = AgentMemoryService(self.db)
        thread_id = f"{user_id}:{agent_id}:{session_id}"
        await memory_service.clear_conversation(agent_id, user_id, thread_id)
        return True

    # ============================================================
    # v2.0: Factory Mode Methods
    # ============================================================

    async def run_with_factory(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        runtime_config: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        v2.0: 使用工厂模式运行 Agent

        工厂模式特性：
        - 每次运行时动态构建图
        - 支持运行时配置覆盖（模型、技能、MCP 服务器）
        - 支持中间件链
        - 支持计划模式

        Args:
            agent_id: Agent ID
            user_id: 用户 ID
            query: 用户输入
            model_config: 模型配置
            runtime_config: 运行时配置覆盖
                {
                    "model_name": "claude-sonnet-4",  # 动态模型选择
                    "plan_mode": True,                # 计划模式
                    "skills": ["skill1", "skill2"],   # 技能覆盖
                    "mcp_servers": ["filesystem"],    # MCP 服务器
                }
            session_id: 会话 ID

        Returns:
            运行结果
        """
        if not self.use_factory_mode or not self.graph_factory:
            # 回退到传统模式
            return await self.run(agent_id, user_id, query, model_config, session_id)

        start_time = time.time()
        run_id = str(uuid4())
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        # 获取 Agent 配置
        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {agent_id}")

        # 使用工厂构建图
        async with self.graph_factory.create_graph(
            agent_config=agent_config,
            runtime_config=runtime_config or {},
            run_id=run_id,
        ) as graph:
            human_message = HumanMessage(content=query)

            sync_db = sync_session_factory()
            try:
                checkpoint_saver = DatabaseCheckpointSaver(sync_db)
                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_saver": checkpoint_saver,
                        # v2.0: 传递运行时配置到 LangGraph
                        "runtime_config": runtime_config or {},
                    }
                }

                memory_service = AgentMemoryService(self.db)
                history = await memory_service.get_conversation(agent_id, user_id, thread_id)

                initial_state = {
                    "messages": history + [human_message],
                    "context": {},
                    "current_step": "start",
                    "metadata": {
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "run_id": run_id,
                    }
                }

                try:
                    result = await graph.ainvoke(initial_state, config=config)

                    messages = result.get("messages", [])
                    response = messages[-1].content if messages else ""

                    await memory_service.add_conversation(
                        agent_id, user_id, thread_id,
                        [query, response],
                        ttl_hours=24
                    )

                    await self._log_call(
                        agent_id, user_id, thread_id, run_id,
                        model_config, "success",
                        input_tokens=0, output_tokens=0,
                        latency_ms=int((time.time() - start_time) * 1000)
                    )

                    return {
                        "run_id": run_id,
                        "response": response,
                        "messages": messages,
                        "factory_mode": True,
                    }

                except Exception as e:
                    await self._log_call(
                        agent_id, user_id, thread_id, run_id,
                        model_config, "error",
                        error_message=str(e)
                    )
                    raise
            finally:
                sync_db.close()

    async def run_stream_with_factory(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        runtime_config: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        v2.0: 使用工厂模式流式运行 Agent

        参数同 run_with_factory
        """
        if not self.use_factory_mode or not self.graph_factory:
            async for chunk in self.run_stream(agent_id, user_id, query, model_config, session_id):
                yield chunk
            return

        run_id = str(uuid4())
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent_config = result.scalar_one_or_none()
        if not agent_config:
            raise ValueError(f"Agent not found: {agent_id}")

        async with self.graph_factory.create_graph(
            agent_config=agent_config,
            runtime_config=runtime_config or {},
            run_id=run_id,
        ) as graph:
            human_message = HumanMessage(content=query)

            sync_db = sync_session_factory()
            try:
                checkpoint_saver = DatabaseCheckpointSaver(sync_db)
                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_saver": checkpoint_saver,
                    }
                }

                memory_service = AgentMemoryService(self.db)
                history = await memory_service.get_conversation(agent_id, user_id, thread_id)

                initial_state = {
                    "messages": history + [human_message],
                    "context": {},
                    "current_step": "start",
                    "metadata": {
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "run_id": run_id,
                    }
                }

                full_response = []
                try:
                    async for event, metadata in graph.astream(
                        initial_state,
                        config=config,
                        stream_mode="messages",
                    ):
                        if hasattr(event, 'content') and event.content:
                            yield event.content
                            full_response.append(event.content)

                    if full_response:
                        await memory_service.add_conversation(
                            agent_id, user_id, thread_id,
                            [query, "".join(full_response)],
                            ttl_hours=24
                        )

                except Exception as e:
                    yield f"[ERROR] {str(e)}"
            finally:
                sync_db.close()
