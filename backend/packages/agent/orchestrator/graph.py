"""主编排图 - 主 Agent 编排 + 子 Agent 子图执行 + 聚合

MVP 采用可稳定落地的实现：
- 主 Agent 决策：LLM 输出 JSON plan（need_sub_agents / run_mode / plan / direct_answer），解析为结构
- 子 Agent：复用 build_tao_graph 执行（含工具能力），支持串行 / 并行
- 聚合：主 Agent 读取全部子结果生成最终回答
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.core.harness.agent.loader import AgentLoader, LoadedAgentConfig, security_policy_for
from packages.agent.orchestrator.state import (
    OrchestrationPlan,
    OrchestratorState,
    SubAgentResult,
    SubTask,
)
from packages.agent.core.harness.config import DEFAULT_USER_ID, RuntimeConfig
from packages.agent.orchestrator.text_utils import (
    extract_final_content,
    make_pii_redactor,
    redact_block,
)
from packages.agent.orchestrator.repositories import (
    ConversationRepository,
    ExecutionTraceRepository,
)
from packages.agent.orchestrator.graph_builder import AgentGraphBuilder
from packages.agent.orchestrator.graph_runtime import GraphRuntime
from packages.agent.orchestrator.dispatcher import TaskDispatcher
from packages.agent.orchestrator.aggregator import ResultAggregator
from packages.agent.schemas.stream import ev_tool

logger = logging.getLogger(__name__)

# 主 Agent 编排提示词：要求输出 JSON plan
MAIN_ORCHESTRATOR_PROMPT = """你是任务编排主 Agent。根据用户的请求，判断是否需要派发给子 Agent 执行。

如果需要子 Agent，输出 JSON（严格键名）：
{
  "need_sub_agents": true,
  "run_mode": "serial" 或 "parallel",
  "plan": [
    {"sub_agent_id": "<子agent的id>", "task_prompt": "<给该子agent的任务描述>"}
  ]
}

如果无需子 Agent，输出：
{
  "need_sub_agents": false,
  "plan": [],
  "direct_answer": "<你直接给出的回答>"
}

只输出 JSON，不要额外文字。
"""

AGGREGATE_PROMPT = """你根据以下多个子 Agent 的执行结果，综合整理成一份面向用户的最终回答。

子 Agent 结果：
{results}

请给出清晰、完整的最终回答。
"""

class OrchestratorRuntime:
    """主编排器：组合 GraphRuntime，专精主 Agent 编排。
    
    Phase 2 重构：
    - 从继承 GraphRuntime 改为组合
    - 通过 _graph_runtime 字段访问通用图执行能力
    """

    def __init__(self, db: AsyncSession, model_name: Optional[str] = None,
                 user_id: Optional[int] = None, config: Optional[RuntimeConfig] = None):
        # Phase 2: 组合 GraphRuntime（不再继承）
        from packages.agent.orchestrator.graph_runtime import GraphRuntime
        self._graph_runtime = GraphRuntime(config)
        
        # 保存 config 供后续使用（注意：config 是 property，不能直接赋值）
        # self._config 已经通过 property 委托给 _graph_runtime.config
        # 这里不需要额外赋值，因为 GraphRuntime 已经保存了 config
        
        self.db = db
        self.loader = AgentLoader(db)
        self.model_name = model_name
        self.user_id = user_id or DEFAULT_USER_ID
        # 数据访问仓库（隔离存储细节，Repository 模式）
        self._conversations = ConversationRepository(db)
        self._traces = ExecutionTraceRepository(db)
        # 图构建器（装配 Harness 组件并编译 TAO 图，Factory 模式）
        self._graph_builder = AgentGraphBuilder(db, self.user_id)
        
        # P1 优化：组合拆分后的类（TaskDispatcher / ResultAggregator）
        # 移除 PlanGenerator：让模型直接通过 tool_calls 决策
        self._task_dispatcher = TaskDispatcher(self)
        # ResultAggregator 需要 LLM，延迟初始化
        self._aggregator: Optional[ResultAggregator] = None
        
        # 运行时状态（方案 B：图驱动）
        self._current_state: Optional[Dict[str, Any]] = None
    
    # =========================================================================
    # 方案 B：图节点方法（Orchestrator 作为 TAO Graph 的节点）
    # =========================================================================
    
    async def execute_step(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        方案 B 核心：Orchestrator 作为图节点的单步执行方法
        
        移除 PlanGenerator：让模型直接通过 tool_calls 决策
        
        职责:
        1. 解析用户意图（从 state.messages）
        2. 直接调用模型，让模型通过 tool_calls 决定是否需要子 Agent
        3. 返回决策给图
        
        不做:
        - 不控制循环（由图决定）
        - 不处理 Hooks（由外部包装器处理）
        - 不管理 Checkpoints（由外部包装器处理）
        
        Args:
            state: AgentState，包含 messages、iteration 等
        
        Returns:
            Dict[str, Any]: 更新后的 state
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        
        # 保存当前状态
        self._current_state = state
        
        messages = state.get("messages", [])
        iteration = state.get("iteration", 0)
        
        # 1. 解析用户意图（从最后一条消息）
        if not messages:
            return state
        
        last_message = messages[-1]
        query = getattr(last_message, "content", "")
        
        # 2. 直接调用模型决策（移除 PlanGenerator 中间层）
        # 模型通过 tool_calls 决定是否需要子 Agent
        llm = await self._create_llm()
        
        # 构建提示词：告诉模型可用子 Agent 列表
        catalog = await self._load_sub_agent_catalog()
        if catalog:
            catalog_text = "\n".join(
                f"- {agent['agent_id']}: {agent['name']} ({agent.get('description', '通用 Agent')})"
                for agent in catalog
            )
            system_prompt = f"""你是任务编排主 Agent。根据用户请求，判断是否需要调用子 Agent。

可用子 Agent：
{catalog_text}

如果需要子 Agent，请调用工具：subagent_spawn(agent_id: str, task_prompt: str)
如果不需要子 Agent，直接生成最终答案。

注意：
- 只从上面列表中选择子 Agent
- agent_id 必须完全匹配
- 可以调用多个子 Agent（串行或并行）
"""
        else:
            system_prompt = """你是智能助手。直接回答用户问题即可。"""
        
        # 绑定 subagent_spawn 工具到 LLM
        from packages.agent.tools.builtins import subagent_spawn
        llm = llm.bind_tools([subagent_spawn])
        
        # 调用模型
        prompt_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        
        try:
            response = await llm.ainvoke(prompt_messages)
        except Exception as e:
            logger.error("[Orchestrator] 模型调用失败：%s", e)
            # 降级：直接返回错误
            state["plan"] = {"need_sub_agents": False, "plan": [], "direct_answer": f"模型调用失败：{e}"}
            state["direct_answer"] = True
            state["iteration"] = iteration + 1
            return state
        
        # 3. 检查模型是否调用了子 Agent
        tool_calls = getattr(response, "tool_calls", [])
        subtasks = []  # 初始化 subtasks
        
        if tool_calls:
            # 模型决定调用子 Agent
            for tc in tool_calls:
                # 只处理 subagent_spawn 工具调用
                if tc.get("name") == "subagent_spawn":
                    args = tc.get("args", {})
                    subtasks.append({
                        "sub_agent_id": args.get("agent_id", ""),
                        "task_prompt": args.get("task_prompt", "")
                    })
            
            if subtasks:
                # 有子任务
                state["subtasks"] = subtasks
                state["plan"] = {
                    "need_sub_agents": True,
                    "plan": subtasks,
                    "run_mode": "serial"  # 默认串行
                }
                state["direct_answer"] = False
            else:
                # 工具调用不是子 Agent，视为直答
                state["plan"] = {"need_sub_agents": False, "plan": [], "direct_answer": response.content}
                state["direct_answer"] = True
        else:
            # 模型没有调用工具，直接生成答案
            state["plan"] = {
                "need_sub_agents": False,
                "plan": [],
                "direct_answer": response.content
            }
            state["direct_answer"] = True
        
        # 4. 返回决策给图
        state["iteration"] = iteration + 1
        state["orchestrator_decision"] = {
            "plan": state.get("plan"),
            "has_subtasks": bool(subtasks),
        }
        
        return state
    
    # Phase 2: 委托方法（原继承自 GraphRuntime）
    @property
    def config(self):
        """委托给 GraphRuntime"""
        return self._graph_runtime.config
    
    def _get_checkpointer(self):
        """委托给 GraphRuntime"""
        return self._graph_runtime._get_checkpointer()
    
    def _build_config(self, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None) -> dict:
        """委托给 GraphRuntime"""
        return self._graph_runtime._build_config(thread_id, run_id, callbacks)
    
    async def execute(self, graph, state: dict, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None):
        """委托给 GraphRuntime"""
        return await self._graph_runtime.execute(graph, state, thread_id, run_id, callbacks)

    async def resume_sub_agent(self, sub_agent_id: str, thread_id: str,
                               main_prompt: Optional[str] = None) -> Dict[str, Any]:
        """审批通过后从断点续跑子 Agent 图（完整 HITL 断点续跑，#3/#4）。

        重载子 Agent 配置 → 同 policy/工具重建图（带 DB checkpointer）→
        `graph.ainvoke(None, config)` 从 checkpointer 保存的中断点继续执行
        （LangGraph 用 None 输入恢复；permission 层已短路放行已批工具）。
        """
        try:
            cfg = await self.loader.load_sub_agent(sub_agent_id)
        except Exception as e:
            return {"success": False, "error": f"子Agent加载失败: {e}", "sub_agent_id": sub_agent_id}

        sub_security = security_policy_for(cfg)

        sub_llm = await self._create_llm()
        tools = self._load_sub_tools(cfg.tools_whitelist)
        if tools:
            try:
                sub_llm = sub_llm.bind_tools(tools)
            except Exception as e:
                logger.warning("[Orchestrator] 续跑子Agent=%s 工具绑定失败: %s", cfg.name, e)

        graph = self._build_agent_graph(
            llm=sub_llm, tools=tools,
            system_prompt=cfg.system_prompt or "你是专业子 Agent。",
            max_iterations=max(1, cfg.max_step),
            security_policy=sub_security or None,
            use_checkpointer=bool(sub_security),
            checkpointer=self._get_checkpointer() if sub_security else None,
        )
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": getattr(self.config, "recursion_limit", None) or 25,
        }
        start = datetime.utcnow()
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(None, config=config), timeout=self.config.timeout_seconds,
            )
            content = extract_final_content(result.get("messages", []))
            if not content:
                for m in result.get("messages", []):
                    if getattr(m, "type", "") in ("ai", "assistant") and getattr(m, "reasoning", None):
                        content = str(m.reasoning)
                        break
            return {
                "success": True, "content": content,
                "sub_agent_id": sub_agent_id, "thread_id": thread_id,
                "duration_ms": int((datetime.utcnow() - start).total_seconds() * 1000),
            }
        except asyncio.TimeoutError:
            return {"success": False, "sub_agent_id": sub_agent_id,
                    "error": f"续跑超时（>{self.config.timeout_seconds}s）"}
        except Exception as e:
            from langgraph.errors import GraphInterrupt
            if isinstance(e, GraphInterrupt):
                approvals = self._extract_approvals(e)
                for a in approvals:
                    a["thread_id"] = thread_id
                return {"success": True, "sub_agent_id": sub_agent_id,
                        "content": "[需要审批] 仍有敏感工具待批准。", "approvals": approvals}
            logger.exception("[Orchestrator] 子 Agent 续跑失败 | thread=%s", thread_id)
            return {"success": False, "sub_agent_id": sub_agent_id, "error": str(e)}

    async def _create_llm(self):
        from packages.agent.schemas.chat import ModelConfig
        from packages.agent.services.agent_runtime_service import create_langchain_llm

        model_name = self.model_name or self.config.default_model
        config = ModelConfig(
            provider=model_name,  # 会作为 model_id 反查真实 provider
            model=model_name,
            temperature=self.config.llm_temperature,
            max_tokens=self.config.llm_max_tokens,
        )
        return await create_langchain_llm(config, self.db)

    async def _load_sub_agent_catalog(self) -> List[Dict[str, str]]:
        """加载子 Agent 目录（用于提示词）。"""
        from packages.agent.services.agent_config_service import AgentConfigService
        
        service = AgentConfigService(self.db)
        agents, _ = await service.list(self.user_id, agent_type="sub")
        return [
            {
                "agent_id": agent.id,
                "name": agent.name,
                "description": agent.description or "通用 Agent",
            }
            for agent in agents
        ]

    # ---------------- 主编排节点 ----------------

    @staticmethod
    def _snapshot_main_config(cfg: Any) -> Dict[str, Any]:
        """主 Agent 配置可序列化快照（统一 State main_agent_config 字段）。"""
        from dataclasses import asdict, is_dataclass
        keep = ("agent_id", "name", "system_prompt", "soul", "claude",
                "sandbox_policy", "tools_whitelist", "require_approval_tools",
                "max_step", "inherit_main_context")
        if is_dataclass(cfg):
            return {k: v for k, v in asdict(cfg).items() if k in keep}
        return {"system_prompt": getattr(cfg, "system_prompt", "")}

    # ---------------- 工具加载 ----------------
    def _load_sub_tools(self, whitelist: List[str]) -> List[Any]:
        """按 tools_whitelist 从 ToolRegistry 加载子 Agent 工具。"""
        try:
            from packages.agent.tools.registry import get_tool_registry
        except Exception:
            return []
        reg = get_tool_registry()
        all_tools = reg.get_all()
        if not whitelist:
            return all_tools
        return [t for t in all_tools if t.name in whitelist]

    # ---------------- 统一图构建（单一内核，装配委托 GraphBuilder）----------------
    def _build_agent_graph(self, llm: Any, tools: Optional[List[Any]] = None,
                           system_prompt: Optional[str] = None, max_iterations: int = 10,
                           on_token: Optional[Any] = None,
                           on_tool_event: Optional[Any] = None,
                           security_policy: Optional[dict] = None,
                           checkpointer: Optional[Any] = None,
                           use_checkpointer: bool = False,
                           agent_config: Optional[dict] = None,
                           sandbox_workdir: Optional[str] = None):
        """统一构建 TAO Graph（装配职责委托 AgentGraphBuilder）。"""
        return self._graph_builder.build(
            llm=llm, tools=tools, system_prompt=system_prompt,
            max_iterations=max_iterations, on_token=on_token,
            on_tool_event=on_tool_event,
            security_policy=security_policy, checkpointer=checkpointer,
            use_checkpointer=use_checkpointer, agent_config=agent_config,
            sandbox_workdir=sandbox_workdir,
        )

    def _make_tool_event_cb(self):
        """构造流向 run_stream 共享 sink 的 tool_event 回调；无活跃流时返回 None。

        用独立 PII redactor 实例脱敏 result，避免与 token 流共用缓冲相互污染。
        """
        sink = getattr(self, "_stream_sink", None)
        if sink is None:
            return None
        redactor = None
        if getattr(self, "_tool_event_redactor", None) is not None:
            from packages.agent.orchestrator.text_utils import make_pii_redactor
            redactor = make_pii_redactor()

        def _redact_str(v: str) -> str:
            if redactor is None:
                # 不截断，保留完整内容
                return v
            head = redactor.push(v) or ""
            tail = redactor.flush() or ""
            return head + tail

        async def on_tool_event(ev):
            data = dict(ev.get("data") or {})
            if isinstance(data.get("result"), str):
                data["result"] = _redact_str(data["result"])
            sink.put_nowait(ev_tool(data))

        return on_tool_event

    # ---------------- 会话保存（记忆/Harness 5 大核心-记忆）----------------
    async def _save_conversation(self, user_id: int, session_id: Optional[str],
                                 query: str, final_output: str,
                                 agent_id: Optional[str] = None) -> None:
        """持久化一轮用户会话到 conversations 表（数据访问委托 Repository）。"""
        await self._conversations.save(
            user_id=user_id, session_id=session_id, query=query,
            final_output=final_output, agent_id=agent_id,
        )

    async def _load_conversation_history(self, user_id: int, session_id: Optional[str],
                                         limit: int = 6) -> List[Any]:
        """读取会话历史（记忆回灌）：返回 LangChain 消息序列（委托 Repository）。"""
        return await self._conversations.load_history(user_id, session_id, limit=limit)

    # ---------------- 执行追踪 ----------------
    async def _save_execution_trace(self, run_id: str, query: str, intent: str,
                                    final_output: str, sub_agents: List[str], user_id: int,
                                    sub_results: Optional[List[Dict]] = None) -> None:
        """记录一次执行追踪（数据访问委托 Repository）。"""
        await self._traces.save_trace(
            run_id=run_id, query=query, intent=intent, final_output=final_output,
            sub_agents=sub_agents, user_id=user_id, sub_results=sub_results,
        )

    # ---------------- 子 Agent 执行（ReAct 循环）---------------
    async def _exec_sub_task(self, llm: Any, sub_task: SubTask, main_prompt: str,
                             state: Optional[Dict[str, Any]] = None,
                             history: Optional[List[Any]] = None) -> SubAgentResult:
        """委托给 TaskDispatcher。"""
        return await self._task_dispatcher.exec_sub_task(
            llm, sub_task, main_prompt, state, history
        )

    async def _run_sub_agent_graph(self, sub_llm: Any, tools: List[Any], sub_system: str,
                                   sub_security: dict, cfg: LoadedAgentConfig,
                                   task_prompt: str,
                                   sandbox_workdir: Optional[str] = None) -> SubAgentResult:
        """子 Agent 图执行（硬超时 + 重试；审批/异常照常返回 SubAgentResult）。"""
        from langchain_core.messages import HumanMessage

        graph = self._build_agent_graph(
            llm=sub_llm,
            tools=tools,
            system_prompt=sub_system,
            max_iterations=max(1, cfg.max_step),
            security_policy=sub_security or None,
            on_tool_event=self._make_tool_event_cb(),
            sandbox_workdir=sandbox_workdir,
            # HITL 断点续跑（#4）：带审批策略时启用 DB checkpointer，中断点在
            # 权限检查前保存断点；审批通过后按 thread_id 从断点续跑。
            use_checkpointer=bool(sub_security),
            checkpointer=self._get_checkpointer() if sub_security else None,
        )

        thread_id = f"{self.user_id}:sub:{cfg.agent_id}:{int(__import__('time').time() * 1000)}"
        # 统一经运行时 execute（上下文压缩 + 重试 + 硬超时）
        res = await self.execute(
            graph, {"messages": [HumanMessage(content=task_prompt)]}, thread_id,
        )
        if not res.success:
            # 审批异常（GraphInterrupt）保留并提取；超时按 run_id 归因
            approvals = self._extract_approvals(res.error)
            if approvals:
                for a in approvals:
                    a["thread_id"] = thread_id
                return SubAgentResult(
                    sub_agent_id=cfg.agent_id, success=True,
                    content="[需要审批] 敏感工具调用已发起审批请求，等待批准后可重试。",
                    approvals=approvals,
                )
            if (res.metadata or {}).get("timeout"):
                logger.warning("[Orchestrator] 子 Agent 执行超时（>%ss）: %s",
                               self.config.timeout_seconds, cfg.agent_id)
                return SubAgentResult(sub_agent_id=cfg.agent_id, success=False,
                                      error=f"子Agent执行超时（>{self.config.timeout_seconds}s）")
            logger.warning("[Orchestrator] 子 Agent 执行失败: %s -> %s",
                           cfg.agent_id, res.error_message)
            return SubAgentResult(sub_agent_id=cfg.agent_id, success=False,
                                  error=res.error_message or "子Agent执行失败")

        state = res.result
        approvals = self._extract_approvals(state)
        if approvals:
            for a in approvals:
                a["thread_id"] = thread_id
            return SubAgentResult(
                sub_agent_id=cfg.agent_id, success=True,
                content="[需要审批] 敏感工具调用已发起审批请求，等待批准后可重试。",
                approvals=approvals,
            )
        content = extract_final_content(state.get("messages", []))
        # 若内容为空且有 reasoning，则使用 reasoning 兜底
        if not content:
            for m in state.get("messages", []):
                if getattr(m, "type", "") in ("ai", "assistant") and getattr(m, "reasoning", None):
                    content = str(m.reasoning)
                    break
        return SubAgentResult(sub_agent_id=cfg.agent_id, success=True, content=content)

    @staticmethod
    def _extract_approvals(state_or_exc: Any) -> List[Dict[str, Any]]:
        """从图结果/异常中提取审批请求（__interrupt__）。"""
        # 1. state 为 dict 且含 __interrupt__
        if isinstance(state_or_exc, dict):
            intr = state_or_exc.get("__interrupt__")
            if intr and isinstance(intr, dict):
                pending = intr.get("pending") or intr.get("value", {}).get("pending") or []
                if intr.get("type") == "approval_required" and pending:
                    return [dict(p) if isinstance(p, dict) else {"tool": str(p)} for p in pending]
        # 2. LangGraph interrupt 异常对象
        try:
            intr = getattr(state_or_exc, "interrupts", None) or getattr(state_or_exc, "value", None)
            if intr:
                return [dict(p) for p in (intr.get("pending") or []) if isinstance(p, dict)]
        except Exception as e:
            logger.debug("[Graph] 提取 pending 失败：%s", e)
            # 降级：返回空列表
        return []

    # ---------------- 指定智能体执行（meta/MCP 工具复用，替代 HarnessEngine）----
    async def execute_agent(self, agent_id: str, query: str,
                            user_id: Optional[int] = None) -> str:
        """把指定智能体作为子任务独立执行，返回其回答（旧 HarnessEngine 兼容入口）。"""
        sub_task = SubTask(sub_agent_id=agent_id, task_prompt=query)
        llm = await self._create_llm()
        res = await self._exec_sub_task(llm, sub_task, "你是通用助手。")
        if res.success:
            return str(res.content)
        return f"执行失败: {res.error}"

    # ---------------- 主 Agent 直接回答（走 tao_graph，middleware 全装配 + 流式）----
    async def _direct_answer_stream(self, query: str, main_prompt: str, main_agent_cfg=None,
                                    session_id: Optional[str] = None):
        """主 Agent 直接回答：经统一图（含 middleware + PII 脱敏）流式输出。

        记忆回灌（Phase 4）：注入本会话历史（最近 N 轮），配合 think 节点的
        PromptAssembler Token 预算压缩，实现"记忆不只写、还能读"。
        """
        from langchain_core.messages import HumanMessage

        main_llm = await self._create_llm()
        redactor = make_pii_redactor()
        q: asyncio.Queue = asyncio.Queue()

        async def on_token(chunk):
            # 区分模型思考（打标 reasoning）与最终答案，前端可分别渲染
            has_reasoning_kwarg = chunk.additional_kwargs.get("reasoning") if hasattr(chunk, 'additional_kwargs') else False
            content = getattr(chunk, "content", "") or ""
            kind = "reasoning" if has_reasoning_kwarg else "content"
            
            # 🔍 打印每个 chunk 的详细信息（用 WARNING 确保能看到）
            logger.warning("[on_token] kind=%s, has_reasoning=%s, content_len=%d", kind, has_reasoning_kwarg, len(content))
            if content:
                logger.warning("  [content_preview] %s", content[:200] if len(content) > 200 else content)
            
            q.put_nowait((kind, content))

        # 直答工具集：由主 Agent 配置白名单驱动（Phase 2），从注册表解析可用工具
        #（含 save_workspace_file 写文件能力 + 其他白名单内可用工具）。
        tools = self._load_sub_tools(
            main_agent_cfg.tools_whitelist if main_agent_cfg is not None else ["save_workspace_file"]
        )
        if tools:
            try:
                main_llm = main_llm.bind_tools(tools)
            except Exception as e:
                logger.warning("[Orchestrator] 直答工具绑定失败，走纯 LLM: %s", e)

        # Harness 分层上下文：有 soul/claude 时经 PromptAssembler 分层组装
        agent_config = None
        if main_agent_cfg is not None and (main_agent_cfg.soul or main_agent_cfg.claude):
            agent_config = {
                "soul": main_agent_cfg.soul,
                "claude": main_agent_cfg.claude,
                "token_budget": (main_agent_cfg.raw or {}).get("token_budget", 8192),
            }

        # 沙箱生命周期（Phase 3）：按主 Agent sandbox_policy 初始化/销毁隔离工作区
        scope = None
        if main_agent_cfg is not None and main_agent_cfg.sandbox_policy:
            from packages.agent.core.harness.sandbox.runtime import SandboxScope
            scope = SandboxScope(
                db=self.db, user_id=self.user_id,
                session_id=getattr(self, "session_id", None),
                policy=main_agent_cfg.sandbox_policy,
            )
        sandbox_workdir = None
        if scope is not None:
            await scope.__aenter__()
            sandbox_workdir = scope.workdir

        graph = self._build_agent_graph(
            llm=main_llm,
            tools=tools,
            system_prompt=main_prompt or "你是通用助手。",
            agent_config=agent_config,
            max_iterations=10,
            on_token=on_token,
            on_tool_event=self._make_tool_event_cb(),
            sandbox_workdir=sandbox_workdir,
        )

        def _redact(text: str) -> str:
            """流式 PII 脱敏。
            
            修复：原实现中，流式脱敏器会缓冲内容等待跨 token 匹配，导致短 token 被完全过滤。
            新策略：直接返回原文，不阻塞流式输出。PII 脱敏应该在内容生成后一次性处理。
            """
            # ✅ 直接返回原文，确保流式输出不被阻塞
            # PII 脱敏的流式处理会破坏跨 token 的敏感信息匹配，应该在完整内容生成后一次性处理
            return text

        thread_id = f"{self.user_id}:main:{int(__import__('time').time() * 1000)}"
        # 记忆回灌（Phase 4）：历史消息 + 当前查询，交由 PromptAssembler 压缩
        history = await self._load_conversation_history(self.user_id, session_id)
        input_messages = history + [HumanMessage(content=query)]
        # 直答图执行包一层整体硬超时：超时后 gtask 结束，已产出的 token 照常发出
        gtask = asyncio.create_task(
            asyncio.wait_for(
                graph.ainvoke(
                    {"messages": input_messages},
                    config=self._build_config(thread_id),
                ),
                timeout=self.config.timeout_seconds,
            )
        )
        try:
            while True:
                try:
                    kind, raw = await asyncio.wait_for(q.get(), timeout=0.1)
                    c = _redact(raw) or ""
                    if c:
                        # 🔍 打印发送到前端的每个 chunk（用 WARNING 确保能看到）
                        logger.warning("[_direct_answer_stream] YIELD kind=%s, content_len=%d", kind, len(c))
                        logger.warning("  [content_preview] %s", c[:200] if len(c) > 200 else c)
                        yield (kind, c)
                except asyncio.TimeoutError:
                    if gtask.done():
                        exc = gtask.exception()
                        if exc and not isinstance(exc, asyncio.CancelledError):
                            # 检查是否是审批中断
                            from langgraph.errors import GraphInterrupt
                            if isinstance(exc, GraphInterrupt):
                                # 提取审批请求并重新抛出，让调用者处理
                                approvals = self._extract_approvals(exc)
                                if approvals:
                                    logger.info("[Orchestrator] 捕获审批请求：%d 个", len(approvals))
                                    # 包装异常，带上审批请求
                                    raise GraphInterrupt(approvals) from exc
                            logger.warning("[Orchestrator] 直答图执行结束（含异常）: %s", exc)
                        while not q.empty():
                            kind, raw = q.get_nowait()
                            c = _redact(raw) or ""
                            if c:
                                yield (kind, c)
                        break
                    continue
            # ✅ 移除 flush 调用，因为_redact 已经不再使用脱敏器
            # if redactor is not None:
            #     tail = redactor.flush()
            #     if tail:
            #         yield ("content", tail)
        finally:
            if not gtask.done():
                gtask.cancel()
            if scope is not None:
                await scope.__aexit__(None, None, None)

    # ---------------- 统一入口 ----------------
    async def run(
        self,
        query: str,
        main_prompt: Optional[str] = None,
        run_mode: str = "serial",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行一次主从编排。返回 {final_answer, sub_tasks, sub_agent_results}。"""
        from packages.agent.orchestrator.business_tools import ensure_business_tools
        from packages.agent.orchestrator.supervisor import NoopSink, build_supervisor_graph

        if user_id is not None:
            self.user_id = user_id

        main_agent_cfg = self.loader.load_main_agent(
            system_prompt=main_prompt or None,
            tools=["save_workspace_file", "execute_code"],
        )
        main_prompt = main_agent_cfg.system_prompt or "你是通用助手，可协调多个子 Agent 完成任务。"

        # 0. 注册业务工具（供子 Agent 白名单绑定），并加载子 Agent 目录
        try:
            await ensure_business_tools(self.db, user_id=self.user_id)
        except Exception as e:
            logger.warning("[Orchestrator] 业务工具注册失败，继续: %s", e)
        catalog = await self.loader.list_sub_agents(user_id)
        # 记忆回灌（#5）：run 亦读历史供编排决策（quick 直答分支直接返回，不受影响）
        history = await self._load_conversation_history(self.user_id, None)

        state: OrchestratorState = {
            "messages": [{"role": "user", "content": query}],
            "session_id": None,
            "trace_id": f"trace_{int(__import__('time').time() * 1000)}",
            "main_agent_config": self._snapshot_main_config(main_agent_cfg),
            "temp_sub_config": None,
            "sub_tasks": [],
            "sub_agent_results": [],
            "final_answer": None,
            "error": None,
        }
        # 与 run_stream 同图：非流式 NoopSink + quick 直答（直接返回 plan.direct_answer，保持旧语义）
        supervisor = build_supervisor_graph(
            self, sink=NoopSink(), query=query, main_prompt=main_prompt, main_agent_cfg=main_agent_cfg,
            catalog=catalog, run_mode=run_mode, allow_sub_agents=True,
            session_id=None, redactor=None, direct_strategy="quick",
            history=history,
        )
        thread_id = f"{self.user_id}:main:{int(__import__('time').time() * 1000)}"
        cfg = {"configurable": {"thread_id": thread_id},
               "recursion_limit": getattr(self.config, "recursion_limit", None) or 25}

        final_state = await supervisor.ainvoke(state, config=cfg)
        self._last_orchestrator_state = dict(final_state)

        return {
            "final_answer": (final_state.get("final_answer") or ""),
            "sub_tasks": final_state.get("sub_tasks") or [],
            "sub_agent_results": final_state.get("sub_agent_results") or [],
        }

    # ---------------- 流式聚合 ----------------
    async def _aggregate_stream(self, llm: Any, results: List[SubAgentResult], main_prompt: str, redactor=None):
        """流式聚合：逐 token 产出最终回答。失败时降级为一次性汇总。
        
        修复：移除流式 PII 脱敏，因为会破坏跨 token 的敏感信息匹配并阻塞流式输出。
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        # ✅ 移除子 Agent 内容的截断，确保聚合时使用完整内容
        results_text = json.dumps(
            [{"sub_agent_id": r.sub_agent_id, "success": r.success, "content": str(r.content), "error": r.error}
             for r in results], ensure_ascii=False)
        prompt = AGGREGATE_PROMPT.replace("{results}", results_text)
        msgs = [SystemMessage(content=main_prompt), HumanMessage(content=prompt)]

        try:
            async for chunk in llm.astream(msgs):
                c = getattr(chunk, "content", "") or ""
                if c:
                    # ✅ 直接返回原文，不阻塞流式输出
                    yield str(c)
        except Exception as e:
            logger.error("[Orchestrator] 流式聚合失败，降级：%s", e)
            parts = [f"【{r.sub_agent_id}】{r.content if r.success else '执行失败：' + str(r.error)}"
                     for r in results]
            block = "以下为子 Agent 执行结果汇总：\n" + "\n".join(parts)
            yield redact_block(redactor, block)

    # ---------------- 流式统一入口 ----------------
    async def run_stream(
        self,
        query: str,
        main_prompt: Optional[str] = None,
        run_mode: str = "serial",
        user_id: Optional[int] = None,
        allow_sub_agents: bool = True,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """主 Agent 统一调度流式入口（async generator）——一切请求由主 Agent 调度。

        产出事件：
        - {"type":"orchestrator_plan","data":{...}}
        - {"type":"sub_agent","data":{sub_agent_id, status:"running"|"done", success?, content?}}
        - {"type":"token","content":...}  聚合/直接回答 的打字机内容

        Args:
            allow_sub_agents: 是否允许主 Agent 派生子 Agent（False 时仅直接回答）
            agent_id: 指定直接用某 Agent 配置执行（DB agent_configs 表），
                而非默认主 Agent（config/default_main_agent/agent.yaml）。传入时
                以该 Agent 的 system_prompt/tools_whitelist/sandbox_policy 为准。
        """
        from packages.agent.orchestrator.business_tools import ensure_business_tools
        from packages.agent.orchestrator.supervisor import build_supervisor_graph

        # 兜底：允许调用方经 run_stream(user_id=...) 传入真实身份，
        # 使会话/追踪/thread_id/权限引擎都归属当前用户（而非构造时的默认值）
        if user_id is not None:
            self.user_id = user_id

        # 主 Agent 配置化（Phase 2）：
        # - 指定 agent_id（点选专属 Agent）→ 以 DB agent_configs 该 Agent 配置执行
        # - 否则 → 本地文件 soul/claude/agent.yaml 驱动
        # API 显式传入 main_prompt 时作覆盖（兜底保持兼容）。
        if agent_id:
            main_agent_cfg = await self.loader.load_sub_agent(agent_id)
            # 指定执行专属 Agent 时默认不派生子 Agent（single 语义），除非显式开启
            if main_prompt:
                main_agent_cfg.system_prompt = main_prompt
        else:
            main_agent_cfg = self.loader.load_main_agent(
                system_prompt=main_prompt or None,
                tools=["save_workspace_file", "execute_code"],
            )
        main_prompt = main_agent_cfg.system_prompt or "你是通用助手，可协调多个子 Agent 完成任务。"
        redactor = make_pii_redactor()

        try:
            await ensure_business_tools(self.db, user_id=self.user_id)
        except Exception as e:
            logger.warning("[Orchestrator] 业务工具注册失败，继续: %s", e)
        catalog = await self.loader.list_sub_agents(user_id)
        # 记忆回灌（#5）：多 Agent 编排也读历史（plan/dispatch/aggregate）
        history = await self._load_conversation_history(self.user_id, session_id)

        # Supervisor 编排图（LangGraph 状态机）：plan →(按 State)→ direct/dispatch → aggregate
        # 共享 sink 队列承载流式事件；本门面后台跑图、drain 队列产出 SSE 事件（沿用直答流式模式）。
        sink: asyncio.Queue = asyncio.Queue()
        state: OrchestratorState = {
            "messages": [{"role": "user", "content": query}],
            "session_id": session_id,
            "trace_id": f"trace_{int(__import__('time').time() * 1000)}",
            "main_agent_config": self._snapshot_main_config(main_agent_cfg),
            "temp_sub_config": None,
            "sub_tasks": [],
            "sub_agent_results": [],
            "final_answer": None,
            "error": None,
        }
        supervisor = build_supervisor_graph(
            self, sink=sink, query=query, main_prompt=main_prompt, main_agent_cfg=main_agent_cfg,
            catalog=catalog, run_mode=run_mode, allow_sub_agents=allow_sub_agents,
            session_id=session_id, redactor=redactor, direct_strategy="graph",
            history=history,
        )
        thread_id = f"{self.user_id}:main:{int(__import__('time').time() * 1000)}"
        # supervisor 图手动构造 config（禁用 checkpointer/interrupt，避免 GraphInterrupt 冒泡挂死）
        cfg = {"configurable": {"thread_id": thread_id},
               "recursion_limit": getattr(self.config, "recursion_limit", None) or 25}

        # 挂载共享 sink 与 PII redactor：子/直答图内的 tool_event 经 _make_tool_event_cb
        # 汇入本流（主+子 Agent 工具调用链统一吃这条 SSE 流）
        self._stream_sink = sink
        self._tool_event_redactor = redactor
        # 运行指标（验收单来源）：drain 时累计工具/产物，图完成后补轮数与终止原因
        tools: set = set()
        files: list = []

        def _acc(ev):
            if isinstance(ev, dict) and ev.get("type") == "tool_event":
                d = ev.get("data") or {}
                if d.get("phase") == "start" and d.get("tool"):
                    tools.add(d["tool"])
                elif d.get("phase") == "done":
                    for f in (d.get("files") or []):
                        rp = f.get("relative_path") if isinstance(f, dict) else None
                        if rp and rp not in files:
                            files.append(f)

        def _emit(ev):
            if ev is not None:
                _acc(ev)
                return ev
            return None

        gtask = asyncio.create_task(supervisor.ainvoke(state, config=cfg))
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(sink.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if gtask.done():
                        if gtask.cancelled():
                            break
                        exc = gtask.exception()
                        while not sink.empty():
                            ev = _emit(sink.get_nowait())
                            if ev is not None:
                                yield ev
                        if exc is not None:
                            logger.warning("[Orchestrator] 编排图异常: %s", exc)
                        break
                    continue
                ev = _emit(ev)
                if ev is not None:
                    yield ev
        finally:
            try:
                if not gtask.done():
                    gtask.cancel()
            finally:
                try:
                    await gtask
                except Exception as e:
                    logger.warning("[Graph] 清理 stream_sink 失败：%s", e)
                self._stream_sink = None
                self._tool_event_redactor = None

        # 图完成后取终态做副作用（会话记忆 + 追踪）
        # gtask 被取消（正常中止路径）是预期内，静默回退；其余真实异常记审计日志而非无痕迹吞掉。
        try:
            final_state = gtask.result()
        except asyncio.CancelledError:
            final_state = state
        except Exception as e:
            logger.warning("[Audit] 编排图终态获取异常，回退初始 state: %s", e, exc_info=True)
            final_state = state
        self._last_orchestrator_state = dict(final_state)
        # 验收单指标：终止原因 + 轮数 + 工具 + 产物文件（供 /execute/stream 的 done 事件使用）
        iteration = final_state.get("iteration") or 0
        self._run_metrics = {
            "reason": "max_iterations" if iteration >= 10 else "completed",
            "rounds": iteration,
            "tools": sorted(tools),
            "files": files,
        }
        # 保留完整答案，不截断（数据库存储也保存完整内容）
        final_answer = final_state.get("final_answer") or ""
        sub_ids = [t.get("sub_agent_id", "") for t in (final_state.get("sub_tasks") or [])]
        intent = "direct_answer" if not sub_ids else "orchestrator"
        await self._save_conversation(user_id=self.user_id, session_id=session_id,
                                      query=query, final_output=final_answer)
        try:
            run_id = f"run_{int(__import__('time').time() * 1000)}"
            await self._save_execution_trace(
                run_id=run_id, query=query, intent=intent,
                final_output=final_answer, sub_agents=sub_ids, user_id=self.user_id,
                sub_results=final_state.get("sub_agent_results") or [],
            )
        except Exception as e:
            logger.warning("[Orchestrator] 追踪保存异常: %s", e)


# ============================================================================
# 别名定义（Phase 4：统一使用 OrchestratorRuntime）
# ============================================================================
# Orchestrator 是 OrchestratorRuntime 的别名，推荐使用 OrchestratorRuntime
# 已移除的别名：
# - StepExecutor → StepDrivenEngineV2
# - StepExecutionRuntime → StepDrivenEngineV2  
# ============================================================================
Orchestrator = OrchestratorRuntime
