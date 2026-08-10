"""
Harness Engine - Harness 层核心引擎

基于 LangGraph 构建，提供开箱即用的完整方案：
- 内置默认提示词
- 工具调用处理
- 规划工具
- 文件系统访问
- 多 Agent 协作模式
- 意图分析 (自主决策使用哪个 Agent)
"""
import logging
import re
from typing import Optional, Any, Dict, List, AsyncGenerator, Tuple
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.runtime import AgentRuntime, ExecutionResult
from packages.agent.harness.config import HarnessConfig, CollaborationMode
from packages.agent.models.agent import AgentConfig

logger = logging.getLogger(__name__)


class HarnessEngine:
    """
    Harness 引擎 - 解决"怎么用"的问题

    基于 LangGraph 构建，提供业务语义层：
    1. 内置提示词模板 (系统提示词/任务提示词)
    2. 内置规划工具 (Plan/Solve/Reflect)
    3. 文件系统访问 (工作空间隔离)
    4. 多 Agent 协作模式 (Supervisor/RoundRobin/Voting)
    5. 领域特定逻辑 (RAG 集成/代码执行沙箱)
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[HarnessConfig] = None,
    ):
        self.db = db
        self.config = config or HarnessConfig()

        # 使用 Runtime 层
        self.runtime = AgentRuntime(
            config=self.config.runtime,
        )

        # 内置组件 (延迟加载)
        self._prompt_templates: Optional[Dict[str, str]] = None
        self._planning_tools: Optional[List[Any]] = None
        self._rag_tools: Optional[List[Any]] = None

        # 初始化 Governance Engine
        from packages.agent.runtime_engine.governance_callback import GovernanceEngine
        self.governance_engine = GovernanceEngine()

    # ============================================================
    # 执行入口
    # ============================================================

    async def execute(
        self,
        query: str,
        agent_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        kb_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Harness 统一执行入口 - 意图驱动

        Args:
            query: 用户问题/指令
            agent_id: 可选，指定 Agent ID (不传时由 Harness 自主决策)
            thread_id: 线程 ID (用于隔离会话)
            kb_ids: 知识库 ID 列表
            session_id: 会话 ID (用于记忆)
            run_id: 运行 ID
            user_id: 用户 ID (用于 Agent 过滤)
            tenant_id: 租户 ID (用于 Agent 过滤)

        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        run_id = run_id or str(uuid4())
        thread_id = thread_id or session_id or str(uuid4())

        # 执行追踪数据
        trace_data = {
            "run_id": run_id,
            "query": query[:200],
            "user_id": user_id,
            "start_time": start_time,
            "steps": [],
        }

        # 1. 意图分析 - 决定使用哪个 Agent
        if agent_id:
            # 用户已指定 Agent
            selected_agent = await self._get_agent_by_id(agent_id)
            intent = "specified"
            trace_data["steps"].append({"step": "agent_selection", "agent_id": agent_id, "intent": "specified"})
        else:
            # Harness 自主决策
            selected_agent, intent = await self._analyze_intent(query, user_id, tenant_id)
            trace_data["steps"].append({
                "step": "intent_analysis",
                "intent": intent,
                "selected_agent_id": selected_agent.id if selected_agent else None,
                "selected_agent_name": selected_agent.name if selected_agent else None,
            })

        # 2. 准备系统提示词 (模块化)
        system_prompt = self._get_system_prompt(
            agent_type=selected_agent.agent_type if selected_agent else "single",
            agent=selected_agent,
            user_input=query,
            user_id=str(user_id) if user_id else "",
            session_id=session_id or "",
        )

        # 3. 准备工具
        tools = await self._get_tools_for_agent(selected_agent, kb_ids)
        trace_data["steps"].append({
            "step": "tool_preparation",
            "tool_count": len(tools),
            "kb_ids": kb_ids,
        })

        # 4. 构建消息
        messages = [{"role": "user", "content": query}]

        # 5. 执行
        result = await self.execute_with_agent(
            agent_type=selected_agent.agent_type if selected_agent else "single",
            messages=messages,
            thread_id=thread_id,
            tools=tools,
            system_prompt=system_prompt,
            run_id=run_id,
            user_id=user_id,
        )

        # 6. 记录执行统计
        latency_ms = int((time.time() - start_time) * 1000)
        trace_data["steps"].append({
            "step": "execution_complete",
            "latency_ms": latency_ms,
            "success": result is not None,
        })

        # 7. 保存执行追踪到数据库
        await self._save_execution_trace(
            run_id=run_id,
            thread_id=thread_id,
            user_id=user_id,
            tenant_id=tenant_id,
            agent_id=selected_agent.id if selected_agent else None,
            agent_name=selected_agent.name if selected_agent else None,
            agent_type=selected_agent.agent_type if selected_agent else "single",
            intent_type=intent,
            latency_ms=latency_ms,
            steps=trace_data["steps"],
            input_summary=query[:500] if query else None,
            output_summary=str(result.result)[:500] if result and result.result else None,
            status="success" if result else "failed",
        )

        logger.info(
            "[HarnessEngine] Execution completed | run=%s intent=%s agent=%s latency=%dms",
            run_id, intent, selected_agent.id if selected_agent else "none", latency_ms
        )

        return result

    async def execute_with_agent(
        self,
        agent_type: str,
        messages: List[Dict[str, str]],
        thread_id: str,
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        collaboration_mode: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Harness 执行入口 - 使用 AgentRuntime 和 TAO Graph

        Args:
            agent_type: Agent 类型 (single, multi, meta)
            messages: 消息历史
            thread_id: 线程 ID
            tools: 工具列表
            system_prompt: 系统提示词
            collaboration_mode: 协作模式 (supervisor, round_robin, voting)
            run_id: 运行 ID
            user_id: 用户 ID

        Returns:
            ExecutionResult: 执行结果
        """
        run_id = run_id or str(uuid4())

        # 1. 准备系统提示词
        if not system_prompt:
            system_prompt = self._get_system_prompt(agent_type)

        # 2. 准备工具
        all_tools = self._get_tools(agent_type, tools)

        # 3. 构建图 (使用 TAO Graph / Orchestration Graph)
        graph = await self._build_graph(
            agent_type=agent_type,
            system_prompt=system_prompt,
            tools=all_tools,
            collaboration_mode=collaboration_mode,
            run_id=run_id,
            user_id=user_id,
        )

        # 4. 使用 AgentRuntime 执行 (带 Governance Callback)
        state = {"messages": messages}
        result = await self.runtime.execute(
            graph=graph,
            state=state,
            thread_id=thread_id,
            run_id=run_id,
            callbacks=[self.governance_engine.get_callback(run_id)],
        )

        return result

    async def execute_stream(
        self,
        query: str,
        agent_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        kb_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Harness 流式执行入口 - 意图驱动

        Args:
            model_name: 可选，前端传来的模型名称，用于覆盖默认模型
        """
        import time
        start_time = time.time()
        run_id = run_id or str(uuid4())
        thread_id = thread_id or session_id or str(uuid4())

        # 1. 意图分析
        if agent_id:
            selected_agent = await self._get_agent_by_id(agent_id)
            intent = "specified"
        else:
            selected_agent, intent = await self._analyze_intent(query, user_id, tenant_id)

        # 2. 准备系统提示词
        system_prompt = self._get_system_prompt(
            selected_agent.agent_type if selected_agent else "single",
            agent=selected_agent,
            user_input=query,
            user_id=str(user_id) if user_id else "",
            session_id=session_id or "",
        )

        # 3. 准备工具
        tools = await self._get_tools_for_agent(selected_agent, kb_ids)

        # 4. 构建消息
        messages = [{"role": "user", "content": query}]

        # 5. 流式执行 - 传递 model_name
        async for event in self.execute_stream_with_agent(
            agent_type=selected_agent.agent_type if selected_agent else "single",
            messages=messages,
            thread_id=thread_id,
            tools=tools,
            system_prompt=system_prompt,
            run_id=run_id,
            user_id=user_id,
            model_name=model_name,
        ):
            yield event

    async def execute_stream_with_agent(
        self,
        agent_type: str,
        messages: List[Dict[str, str]],
        thread_id: str,
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        collaboration_mode: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        model_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Harness 流式执行 (内部方法)

        - 通过 asyncio.Queue 桥接 think 节点内的 LLM 流式 chunk，
          并实时产出 {type: "token", content} 事件（打字机效果）
        - EOF 产出 {type: "complete", data: ...}

        Args:
            model_name: 可选，前端传来的模型名称，用于覆盖默认模型
        """
        import asyncio

        run_id = run_id or str(uuid4())

        # 1. 准备系统提示词
        if not system_prompt:
            system_prompt = self._get_system_prompt(agent_type)

        # 2. 准备工具
        all_tools = tools or []

        # 3. 构建 token 桥接队列
        token_queue: asyncio.Queue = asyncio.Queue()

        async def on_token(chunk):
            token_queue.put_nowait(chunk)

        # 4. 构建图 - 传递 model_name + on_token
        graph = await self._build_graph(
            agent_type=agent_type,
            system_prompt=system_prompt,
            tools=all_tools,
            collaboration_mode=collaboration_mode,
            run_id=run_id,
            user_id=user_id,
            model_name=model_name,
            on_token=on_token,
        )

        state = {"messages": messages}

        # 5. 后台执行图（非流式 ainvoke），同时逐 token 产出
        async def run_graph():
            return await self.runtime.execute(
                graph=graph,
                state=state,
                thread_id=thread_id,
                run_id=run_id,
                callbacks=[self.governance_engine.get_callback(run_id)],
            )

        gtask = asyncio.create_task(run_graph())

        def _emit(chunk):
            content = getattr(chunk, "content", "") or ""
            return content

        try:
            emitted = False
            while True:
                try:
                    chunk = await asyncio.wait_for(token_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if gtask.done():
                        # 图已结束，排空剩余 token
                        while not token_queue.empty():
                            chunk = token_queue.get_nowait()
                            content = _emit(chunk)
                            if content:
                                emitted = True
                                yield {"type": "token", "run_id": run_id, "content": content}
                        break
                    continue
                content = _emit(chunk)
                if content:
                    emitted = True
                    yield {"type": "token", "run_id": run_id, "content": content}

            # 等待图任务完成（吸收可能的异常）
            await gtask
        except asyncio.CancelledError:
            if not gtask.done():
                gtask.cancel()
            raise
        except Exception as e:
            logger.exception("[HarnessEngine] Stream execution failed | run=%s", run_id)
            yield {"type": "error", "run_id": run_id, "error": str(e)}
        finally:
            if not gtask.done():
                try:
                    gtask.cancel()
                except Exception:
                    pass

    # ============================================================
    # 意图分析与 Agent 选择
    # ============================================================

    async def _analyze_intent(
        self,
        query: str,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Optional[AgentConfig], str]:
        """
        分析用户意图，决定使用哪个 Agent
        """
        # 1. 检查是否是简单问答 (无需 Agent)
        if self._is_general_question(query):
            return None, "general"

        # 2. 获取可用 Agent 列表
        agents = await self._get_available_agents(user_id, tenant_id)

        if not agents:
            return None, "general"

        # 3. 基于关键词 + 语义匹配选择 Agent
        matched_agent = self._match_agent_by_intent(query, agents)
        if matched_agent:
            return matched_agent, "agent"

        # 4. 默认使用第一个 Agent
        return agents[0] if agents else None, "default"

    async def _get_available_agents(
        self,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> List[AgentConfig]:
        """获取可用 Agent 列表"""
        from sqlalchemy import or_

        conditions = [AgentConfig.status == "active"]

        if user_id:
            user_agents = select(AgentConfig).where(
                AgentConfig.user_id == user_id,
                AgentConfig.status == "active"
            )
            result = await self.db.execute(user_agents)
            user_agents_list = result.scalars().all()
            if user_agents_list:
                user_agents_list.sort(key=lambda a: a.total_runs, reverse=True)
                return user_agents_list[:10]

        if tenant_id:
            conditions.append(
                or_(
                    AgentConfig.tenant_id == tenant_id,
                    AgentConfig.is_public == True,
                )
            )
        else:
            conditions.append(AgentConfig.is_public == True)

        result = await self.db.execute(
            select(AgentConfig)
            .where(*conditions)
            .order_by(AgentConfig.total_runs.desc())
            .limit(10)
        )
        return list(result.scalars().all())

    def _is_general_question(self, query: str) -> bool:
        """判断是否是简单问答"""
        general_patterns = [
            r"^你好",
            r"^hello",
            r"^hi\b",
            r"^你是谁",
            r"^你可以做什么",
            r"^介绍一下",
            r"^help\b",
        ]

        for pattern in general_patterns:
            if re.search(pattern, query.lower()):
                return True

        if len(query.strip()) < 10:
            return True

        return False

    def _match_agent_by_intent(
        self,
        query: str,
        agents: List[AgentConfig],
    ) -> Optional[AgentConfig]:
        """基于意图匹配 Agent"""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for agent in agents:
            if agent.name.lower() in query_lower:
                return agent

        domain_keywords = {
            "代码": ["代码", "编程", "脚本", "函数", "debug", "bug"],
            "文档": ["文档", "知识库", "资料", "文件", "search", "检索"],
            "数据分析": ["分析", "数据", "统计", "报表", "chart", "graph"],
            "写作": ["写作", "文章", "报告", "邮件", "文案", "翻译"],
            "问答": ["问题", "帮助", "解答", "咨询", "faq"],
        }

        agent_scores = []

        for agent in agents:
            score = 0
            agent_text = f"{agent.name} {agent.description or ''}".lower()
            agent_words = set(agent_text.split())

            for domain, keywords in domain_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in query_lower:
                        if domain.lower() in agent_text or any(kw.lower() in agent_text for kw in keywords):
                            score += 10
                            break

            overlap = len(query_words & agent_words)
            if overlap > 0:
                score += overlap * 2

            score += min(agent.total_runs / 100, 5)
            agent_scores.append((agent, score))

        agent_scores.sort(key=lambda x: x[1], reverse=True)

        if agent_scores and agent_scores[0][1] > 0:
            return agent_scores[0][0]

        return None

    async def _get_agent_by_id(self, agent_id: str) -> Optional[AgentConfig]:
        """根据 ID 获取 Agent"""
        result = await self.db.execute(
            select(AgentConfig).where(AgentConfig.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def _get_tools_for_agent(
        self,
        agent: Optional[AgentConfig],
        kb_ids: Optional[List[str]] = None,
    ) -> List[Any]:
        """获取 Agent 的工具列表"""
        tools = []

        # 1. 内置工具
        if self.config.enable_planning_tools:
            tools.extend(self._get_planning_tools())

        # 2. RAG 工具
        if kb_ids or (agent and agent.retrieval_enabled):
            tools.extend(self._get_rag_tools(kb_ids or agent.kb_ids if agent else []))

        # 3. 代码工具 (沙箱)
        if self.config.enable_code_tools:
            tools.extend(self._get_code_tools(agent))

        return tools

    # ============================================================
    # 系统提示词构建 (模块化)
    # ============================================================

    def _get_system_prompt(
        self,
        agent_type: str,
        agent: Optional[AgentConfig] = None,
        tools: Optional[List[Any]] = None,
        user_input: str = "",
        user_id: str = "",
        session_id: str = "",
    ) -> str:
        """获取系统提示词 - 模块化构建"""
        from packages.agent.prompts.builder import PromptBuilder, PromptBuildContext

        builder = PromptBuilder()

        # 从 Agent 配置提取安全策略（如有）
        security_policy = {}
        if agent and getattr(agent, "security_policy", None):
            security_policy = agent.security_policy or {}

        ctx = PromptBuildContext(
            agent_id=agent.id if agent else "default",
            agent_type=agent_type,
            agent_name=agent.name if agent else "AI Assistant",
            tools=tools or [],
            security_policy=security_policy,
            user_input=user_input,
            user_id=user_id,
            session_id=session_id,
        )

        return builder.build(ctx)

    def _default_single_agent_prompt(self) -> str:
        """默认单 Agent 提示词 (回退)"""
        return """You are a helpful AI assistant.

Follow these guidelines:
1. Be helpful, harmless, and honest
2. If you don't know something, say so
3. Break down complex tasks into smaller steps
4. Use tools when needed to complete tasks

Think step by step before providing your final answer."""

    def _default_multi_agent_prompt(self) -> str:
        """默认多 Agent 提示词"""
        return """You are part of a multi-agent team working together to solve complex tasks.

Your role:
1. Understand your specific role and expertise
2. Collaborate with other agents when needed
3. Contribute your specialized knowledge
4. Integrate results from other agents

Work together to achieve the best outcome for the user."""

    def _default_meta_agent_prompt(self) -> str:
        """默认 Meta Agent 提示词"""
        return """You are a Meta Agent with the ability to create and execute other agents.

Your capabilities:
1. Analyze user requirements
2. Decide whether to create a new agent or use existing ones
3. Create specialized agents for specific tasks
4. Execute agents and integrate their results

Think carefully about the best approach for each task."""

    def _load_prompt_templates(self) -> Dict[str, str]:
        """加载提示词模板（从数据库或文件）"""
        return {}

    # ============================================================
    # 内置工具
    # ============================================================

    def _get_tools(
        self,
        agent_type: str,
        user_tools: Optional[List[Any]] = None,
    ) -> List[Any]:
        """获取工具列表"""
        tools = []

        # 1. 内置规划工具
        if self.config.enable_planning_tools:
            tools.extend(self._get_planning_tools())

        # 2. RAG 工具
        if self.config.enable_rag_tools:
            tools.extend(self._get_rag_tools())

        # 3. 代码执行工具
        if self.config.enable_code_tools:
            tools.extend(self._get_code_tools())

        # 4. 用户工具
        if user_tools:
            tools.extend(user_tools)

        return tools

    def _get_planning_tools(self) -> List[Any]:
        """获取规划工具"""
        if self._planning_tools is None:
            self._planning_tools = self._create_planning_tools()
        return self._planning_tools

    def _create_planning_tools(self) -> List[Any]:
        """创建规划工具 (Plan/Solve/Reflect)"""
        from langchain_core.tools import tool

        @tool
        async def plan_task(task: str) -> str:
            """Create a plan for completing a task."""
            return f"Plan created for: {task}"

        @tool
        async def solve_step(step: str) -> str:
            """Solve a single step of a plan."""
            return f"Solved step: {step}"

        @tool
        async def reflect_on_result(result: str) -> str:
            """Reflect on the result and identify improvements."""
            return f"Reflection on: {result}"

        return [plan_task, solve_step, reflect_on_result]

    def _get_rag_tools(self, kb_ids: Optional[List[str]] = None) -> List[Any]:
        """获取 RAG 工具"""
        return []

    def _get_code_tools(self, agent: Optional[AgentConfig] = None) -> list:
        """获取代码执行工具 — 沙箱封装为 @tool"""
        from langchain_core.tools import tool

        # 检查 Agent 安全策略是否允许代码执行（如有配置）
        if agent:
            security_policy = getattr(agent, "security_policy", None) or {}
            blocked_tools = security_policy.get("blocked_tools", [])

            if "execute_code" in blocked_tools or "code_interpreter" in blocked_tools:
                logger.info("[HarnessEngine] Code execution blocked by security_policy")
                return []

        # 沙箱工具
        try:
            from packages.agent.sandbox.nsjail import NsJailSandboxManager
            sandbox_manager = NsJailSandboxManager()
        except Exception as e:
            logger.warning(f"[HarnessEngine] Sandbox not available: {e}")
            return []

        @tool
        async def execute_code_in_sandbox(code: str, language: str = "python", timeout: int = 30) -> str:
            """在安全沙箱中执行代码。

            当需要执行用户提供的代码、运行计算、数据处理时使用此工具。
            代码在隔离的 NsJail 沙箱中运行，无法访问网络和文件系统（除指定目录）。

            Args:
                code: 要执行的代码
                language: 编程语言，默认 python
                timeout: 超时时间（秒），默认 30
            """
            try:
                result = await sandbox_manager.execute(
                    code=code,
                    language=language,
                    timeout=timeout,
                )
                return f"执行成功:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            except Exception as e:
                return f"执行失败：{e}"

        return [execute_code_in_sandbox]

    # ============================================================
    # 图构建
    # ============================================================

    async def _build_graph(
        self,
        agent_type: str,
        system_prompt: str,
        tools: List[Any],
        collaboration_mode: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        model_name: Optional[str] = None,
        on_token: Optional[Any] = None,
    ) -> Any:
        """
        构建 LangGraph - 使用 Harness 架构的 TAO Graph 和 Orchestration Graph

        Args:
            model_name: 可选，前端传来的模型名称，用于覆盖默认模型
            on_token: 流式 token 回调 async (chunk) -> None
        """
        from langchain_core.messages import SystemMessage

        # 创建 LLM - 传递 model_name
        llm = await self._create_llm(system_prompt, tools, model_name)

        # 根据 agent_type 选择图的构建方式
        if agent_type == "multi" and collaboration_mode:
            graph = await self._build_orchestration_graph(
                llm=llm,
                system_prompt=system_prompt,
                tools=tools,
                collaboration_mode=collaboration_mode,
            )
        elif agent_type == "meta":
            graph = await self._build_tao_graph(
                llm=llm,
                system_prompt=system_prompt,
                tools=tools,
                max_iterations=15,
                run_id=run_id,
                user_id=user_id,
                on_token=on_token,
            )
        else:
            graph = await self._build_tao_graph(
                llm=llm,
                system_prompt=system_prompt,
                tools=tools,
                max_iterations=10,
                run_id=run_id,
                user_id=user_id,
                on_token=on_token,
            )

        return graph

    async def _build_tao_graph(
        self,
        llm: Any,
        system_prompt: str,
        tools: List[Any],
        max_iterations: int = 10,
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        on_token: Optional[Any] = None,
    ) -> Any:
        """构建 TAO Graph - Think-Act-Observe 循环"""
        from packages.agent.runtime_engine.tao_graph import build_tao_graph
        from packages.agent.output.governance import OutputGovernanceNode
        from langchain_core.messages import SystemMessage

        # 输出治理节点
        output_governance = OutputGovernanceNode(
            llm=llm,
            enable_structured=self.config.enable_structured_output if hasattr(self.config, 'enable_structured_output') else False,
        )

        # 权限引擎 (从 Manifest 加载)
        # 注意：这里简化处理，实际应该从 Agent 配置加载
        permission_engine = None

        graph = build_tao_graph(
            llm=llm,
            tools=tools,
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            enable_output_governance=True,
            output_governance_node=output_governance,
            system_prompt=system_prompt,
            on_token=on_token,
        )

        return graph

    async def _build_orchestration_graph(
        self,
        llm: Any,
        system_prompt: str,
        tools: List[Any],
        collaboration_mode: str,
    ) -> Any:
        """构建 Orchestration Graph - 多 Agent 编排图"""
        from packages.agent.runtime_engine.orchestration_graph import OrchestrationGraphBuilder

        workers = []  # TODO: 从配置中加载 workers

        builder = OrchestrationGraphBuilder(workers=workers)
        graph = builder.build(mode=collaboration_mode)

        return graph

    async def _create_llm(
        self,
        system_prompt: str,
        tools: List[Any],
        model_name: Optional[str] = None,
    ) -> Any:
        """创建 LLM 实例

        Args:
            model_name: 可选，前端传来的模型名称，用于覆盖默认模型
        """
        from packages.agent.services.agent_runtime_service import create_langchain_llm
        from packages.agent.schemas.chat import ModelConfig

        # 如果前端传了 model_name，使用前端传来的模型
        if model_name:
            # 尝试从 model_name 解析 provider 和 model
            # 格式可能是："qwen3.5-397b" 或 "qwen3.5-397b/qwen3.5-397b-a17b"
            parts = model_name.split("/")
            if len(parts) >= 2:
                provider = parts[0]
                model = parts[1]
            else:
                provider = model_name
                model = model_name

            model_config = ModelConfig(
                provider=provider,
                model=model,
                temperature=0.7,
                max_tokens=4096,
            )
        else:
            # 使用默认模型
            model_config = ModelConfig(
                provider="qwen3.5-397b",
                model="qwen3.5-397b-a17b",
                temperature=0.7,
                max_tokens=4096,
            )

        llm = await create_langchain_llm(model_config, self.db)

        if tools:
            llm = llm.bind_tools(tools)

        return llm

    async def _save_execution_trace(
        self,
        run_id: str,
        thread_id: str,
        user_id: Optional[int],
        tenant_id: Optional[str],
        agent_id: Optional[str],
        agent_name: Optional[str],
        agent_type: str,
        intent_type: str,
        latency_ms: int,
        steps: list,
        input_summary: Optional[str],
        output_summary: Optional[str],
        status: str,
    ) -> None:
        """保存执行追踪到数据库"""
        try:
            from packages.agent.models.execution_trace import ExecutionTrace

            trace = ExecutionTrace(
                run_id=run_id,
                thread_id=thread_id,
                user_id=user_id or 1,
                tenant_id=tenant_id,
                agent_id=agent_id,
                agent_name=agent_name,
                agent_type=agent_type,
                intent_type=intent_type,
                status=status,
                latency_ms=latency_ms,
                steps=steps,
                input_summary=input_summary,
                output_summary=output_summary,
            )

            self.db.add(trace)
            await self.db.commit()

            logger.info(
                "[HarnessEngine] Execution trace saved | run=%s user=%s agent=%s",
                run_id, user_id, agent_id
            )
        except Exception as e:
            logger.warning("[HarnessEngine] Failed to save execution trace: %s", e)
            await self.db.rollback()


async def create_harness_engine(
    db: AsyncSession,
    config: Optional[HarnessConfig] = None,
) -> HarnessEngine:
    """创建 HarnessEngine 实例"""
    return HarnessEngine(db=db, config=config)
