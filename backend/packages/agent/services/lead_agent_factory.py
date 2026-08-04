"""
Lead Agent Factory
主智能体工厂函数 - 每次执行时动态创建 Lead Agent

架构设计：
- Lead Agent (主智能体): 通过 make_lead_agent() 工厂函数动态创建
- Subagent (子智能体): 由 Lead Agent 通过 task 工具动态唤起
"""
import logging
from typing import Optional, Any, AsyncGenerator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph_sdk.runtime import ServerRuntime

from packages.agent.models.agent import AgentConfig
from packages.agent.schemas.chat import ModelConfig

logger = logging.getLogger("app.services.lead_agent_factory")


# ============================================================
# Agent State
# ============================================================

from typing import TypedDict, List, Dict, Any
from langchain_core.messages import BaseMessage


class LeadAgentState(TypedDict, total=False):
    """
    Lead Agent 运行时状态

    使用 TypedDict 以便 LangGraph 正确处理
    """
    messages: List[Any]
    context: Dict[str, Any]
    current_step: str
    metadata: Dict[str, Any]
    plan: List[str]
    todo_list: List[Dict[str, Any]]
    subagent_results: Dict[str, Any]


# ============================================================
# Task Tool - 用于唤起子智能体
# ============================================================

def create_task_tool(lead_agent_context: dict) -> Callable:
    """
    创建 task 工具，用于 Lead Agent 唤起子智能体

    Args:
        lead_agent_context: Lead Agent 的上下文信息

    Returns:
        LangChain 工具函数
    """

    @tool
    async def delegate_to_subagent(
        task_description: str,
        subagent_type: str,
        expected_output: str,
        priority: str = "normal",
    ) -> str:
        """
        将任务委托给子智能体执行

        Args:
            task_description: 任务描述
            subagent_type: 子智能体类型 (如 "code_analyzer", "doc_writer", "researcher")
            expected_output: 期望的输出格式
            priority: 优先级 (low, normal, high, critical)

        Returns:
            子智能体的执行结果
        """
        logger.info(
            "[LeadAgent] Delegating task to subagent: type=%s, priority=%s",
            subagent_type, priority
        )

        # 获取子智能体服务
        subagent_service = lead_agent_context.get("subagent_service")
        if not subagent_service:
            return "[ERROR] Subagent service not available"

        # 唤起子智能体
        try:
            result = await subagent_service.execute(
                subagent_type=subagent_type,
                task=task_description,
                expected_output=expected_output,
                parent_context=lead_agent_context,
            )
            return result
        except Exception as e:
            logger.error("Subagent execution failed: %s", e)
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
        subagent_type: Type of subagent needed (code_analyzer, doc_writer, researcher, etc.)
        expected_output: Description of the expected output format
        priority: Task priority level (low, normal, high, critical)

    Returns:
        The subagent's execution result
    """

    return delegate_to_subagent


# ============================================================
# Middleware Components
# ============================================================

class LeadAgentMiddleware:
    """Lead Agent 中间件基类"""

    async def pre_process(self, state: LeadAgentState) -> LeadAgentState:
        return state

    async def post_process(self, state: LeadAgentState) -> LeadAgentState:
        return state


class PlanMiddleware(LeadAgentMiddleware):
    """计划模式中间件"""

    async def pre_process(self, state: LeadAgentState) -> LeadAgentState:
        if "todo_list" not in state:
            state["todo_list"] = []
        if "completed_tasks" not in state:
            state["completed_tasks"] = []
        return state

    async def post_process(self, state: LeadAgentState) -> LeadAgentState:
        # 从消息中提取新任务
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = str(getattr(last_msg, 'content', ''))

            # 简单的任务提取逻辑
            if '[TASK]' in content:
                import re
                tasks = re.findall(r'\[TASK\](.*?)\[/TASK\]', content)
                for task in tasks:
                    task_item = {"description": task.strip(), "status": "pending"}
                    if task_item not in state["todo_list"]:
                        state["todo_list"].append(task_item)

        return state


class LoggingMiddleware(LeadAgentMiddleware):
    """日志中间件"""

    def __init__(self, agent_id: str, run_id: str, user_id: int):
        self.agent_id = agent_id
        self.run_id = run_id
        self.user_id = user_id

    async def pre_process(self, state: LeadAgentState) -> LeadAgentState:
        logger.info(
            "[LeadAgent:%s] [Run:%s] [User:%s] Pre-process | step=%s",
            self.agent_id, self.run_id, self.user_id,
            state.get("current_step", "unknown")
        )
        return state

    async def post_process(self, state: LeadAgentState) -> LeadAgentState:
        logger.info(
            "[LeadAgent:%s] [Run:%s] [User:%s] Post-process | step=%s",
            self.agent_id, self.run_id, self.user_id,
            state.get("current_step", "unknown")
        )
        return state


# ============================================================
# Component Loaders
# ============================================================

class LeadAgentModelLoader:
    """Lead Agent 模型加载器"""

    def __init__(self, model_gateway: Any, db: Any = None):
        self.model_gateway = model_gateway
        self.db = db

    async def load_model(
        self,
        requested_model_name: Optional[str],
        default_config: dict,
    ) -> Any:
        """加载模型"""
        if requested_model_name:
            model_config = await self.model_gateway.get_model_by_name(requested_model_name)
            if model_config:
                return await self._create_llm(model_config)

        # 回退到默认模型
        if default_config:
            model_config = ModelConfig(**default_config)
            return await self._create_llm(model_config)

        raise ValueError("No model configuration available")

    async def _create_llm(self, model_config: ModelConfig) -> Any:
        from packages.agent.services.agent_runtime_service import create_langchain_llm
        return await create_langchain_llm(model_config, self.db)


class LeadAgentToolLoader:
    """Lead Agent 工具加载器"""

    def __init__(self, mcp_loader: Any, skill_loader: Any):
        self.mcp_loader = mcp_loader
        self.skill_loader = skill_loader

    async def load_tools(
        self,
        enabled_mcp_servers: list[str],
        enabled_skills: list[str],
        lead_agent_context: dict,
    ) -> list:
        """加载所有工具"""
        tools = []

        # 1. 加载 MCP 工具
        mcp_tools = await self.mcp_loader.load_tools(enabled_mcp_servers)
        tools.extend(mcp_tools)

        # 2. 加载技能
        skill_tools = await self.skill_loader.load_skills(enabled_skills)
        tools.extend(skill_tools)

        # 3. 添加 task 工具（用于唤起子智能体）
        task_tool = create_task_tool(lead_agent_context)
        tools.append(task_tool)

        return tools


# ============================================================
# Lead Agent Factory
# ============================================================

class LeadAgentFactory:
    """
    Lead Agent 工厂

    每次执行时动态创建 Lead Agent 图

    架构设计：
    - Lead Agent (主智能体): 通过 make_lead_agent() 工厂函数动态创建
    - Subagent (子智能体): 由 Lead Agent 通过 task 工具动态唤起
    """

    def __init__(
        self,
        model_gateway: Any,
        skill_registry: Any,
        db: Any,
        subagent_service: Optional[Any] = None,
    ):
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self.db = db
        self._subagent_service = subagent_service

        # 初始化加载器 - 传递 db 给 model_loader
        self.model_loader = LeadAgentModelLoader(model_gateway, db)
        self.mcp_loader = None
        self.skill_loader = None

    @property
    def subagent_service(self) -> Optional[Any]:
        """获取子智能体服务"""
        return self._subagent_service

    @subagent_service.setter
    def subagent_service(self, value: Any):
        """设置子智能体服务"""
        self._subagent_service = value

    def _create_middlewares(
        self,
        extensions_config: dict,
        agent_id: str,
        run_id: str,
        user_id: int,
    ) -> list[LeadAgentMiddleware]:
        """创建中间件链"""
        middlewares = []

        # 计划模式中间件
        if extensions_config.get("plan_mode_enabled", False):
            middlewares.append(PlanMiddleware())

        # 日志中间件（始终启用）
        middlewares.append(LoggingMiddleware(agent_id, run_id, user_id))

        return middlewares

    async def _apply_middlewares(
        self,
        state: LeadAgentState,
        middlewares: list[LeadAgentMiddleware],
        phase: str = "pre_process",
    ) -> LeadAgentState:
        """应用中间件链"""
        for mw in middlewares:
            try:
                if phase == "pre_process":
                    state = await mw.pre_process(state)
                else:
                    state = await mw.post_process(state)
            except Exception as e:
                logger.error("Middleware %s failed: %s", mw.__class__.__name__, e)
        return state

    @asynccontextmanager
    async def create_lead_agent(
        self,
        agent_config: AgentConfig,
        runtime_config: dict,
        run_id: str,
        user_id: int,
    ) -> AsyncGenerator[Any, None]:
        """
        创建 Lead Agent 图

        这是核心工厂函数，每次执行时被调用

        Args:
            agent_config: Agent 配置（从数据库）
            runtime_config: 运行时配置
            run_id: 运行 ID
            user_id: 用户 ID

        Yields:
            编译后的 LangGraph
        """
        # ========================================================
        # 1. 解析配置
        # ========================================================

        extensions_config = agent_config.extensions_config or {}
        default_model_config = agent_config.default_model_config or {}

        # 运行时覆盖配置
        requested_model = runtime_config.get("model_name")
        enabled_skills = runtime_config.get(
            "skills",
            agent_config.enabled_skills or []
        )
        enabled_mcp_servers = runtime_config.get(
            "mcp_servers",
            extensions_config.get("mcp_servers_enabled", [])
        )

        # ========================================================
        # 2. 准备 Lead Agent 上下文
        # ========================================================

        lead_agent_context = {
            "agent_id": agent_config.id,
            "user_id": user_id,
            "run_id": run_id,
            "subagent_service": self.subagent_service,
            "model_gateway": self.model_gateway,
            "db": self.db,
        }

        # ========================================================
        # 3. 动态加载组件
        # ========================================================

        # 3.1 加载模型
        llm = await self.model_loader.load_model(
            requested_model,
            default_model_config
        )

        # 3.2 加载工具（包括 task 工具）
        # TODO: 初始化 MCP 和 Skill 加载器
        tools = []

        # 添加 task 工具
        task_tool = create_task_tool(lead_agent_context)
        tools.append(task_tool)

        # 绑定工具到 LLM
        if tools:
            llm = llm.bind_tools(tools)

        # ========================================================
        # 4. 构建 Lead Agent 图
        # ========================================================

        async def lead_agent_node(state: LeadAgentState):
            """
            Lead Agent 核心节点

            职责：
            1. 理解用户意图
            2. 制定计划
            3. 决定是否需要调用子智能体
            4. 整合结果并返回
            """
            from langchain_core.messages import SystemMessage

            # 安全获取 messages，兼容 dict 和 LeadAgentState
            messages = state.get("messages", []) if hasattr(state, "get") else state["messages"]
            system_prompt = agent_config.system_prompt

            # 注入系统提示词
            if messages and not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=system_prompt)] + messages
            elif not messages:
                messages = [SystemMessage(content=system_prompt)]

            # 调用 LLM
            response = llm.invoke(messages)

            return {
                "messages": messages + [response],
            }

        # 创建图
        graph = StateGraph(LeadAgentState)
        graph.add_node("lead_agent", lead_agent_node)
        graph.add_edge(START, "lead_agent")
        graph.add_edge("lead_agent", END)

        # 编译并返回
        compiled_graph = graph.compile()

        logger.info(
            "[LeadAgent] Graph built | agent=%s model=%s tools=%d",
            agent_config.id,
            requested_model or default_model_config.get("model", "default"),
            len(tools),
        )

        yield compiled_graph

        # 清理逻辑（可选）

    async def build_and_run(
        self,
        agent_id: str,
        user_id: int,
        query: str,
        runtime_config: dict,
    ) -> dict:
        """
        构建并运行 Lead Agent

        这是便捷方法，封装了完整的执行流程
        """
        from sqlalchemy import select

        run_id = str(uuid4())

        # 获取 Agent 配置
        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        agent_config = result.scalar_one_or_none()

        if not agent_config:
            raise ValueError(f"Agent not found: {agent_id}")

        # 使用工厂构建并运行
        async with self.create_lead_agent(
            agent_config=agent_config,
            runtime_config=runtime_config,
            run_id=run_id,
            user_id=user_id,
        ) as graph:
            from langchain_core.messages import HumanMessage
            from packages.agent.services.agent_checkpoint_service import DatabaseCheckpointSaver
            from packages.core.database import engine
            from sqlalchemy.orm import sessionmaker

            # 创建同步 Session
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

                initial_state = LeadAgentState(
                    messages=[HumanMessage(content=query)],
                    metadata={
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "run_id": run_id,
                    }
                )

                result = await graph.ainvoke(initial_state, config=config)

                messages = result.get("messages", [])
                response = messages[-1].content if messages else ""

                return {
                    "run_id": run_id,
                    "response": response,
                    "messages": messages,
                    "factory_mode": True,
                    "agent_type": "lead_agent",
                }

            finally:
                sync_db.close()
