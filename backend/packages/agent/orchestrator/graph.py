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
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.orchestrator.agent_loader import AgentLoader, LoadedAgentConfig
from packages.agent.orchestrator.state import (
    OrchestrationPlan,
    OrchestratorState,
    SubAgentResult,
    SubTask,
)
from packages.agent.runtime.config import RuntimeConfig
from packages.agent.runtime.state import ExecutionResult
from packages.agent.runtime_engine.tao_graph import build_tao_graph

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
    """主从编排执行运行时（MVP 函数式，便于测试与集成）。"""

    def __init__(self, db: AsyncSession, model_name: Optional[str] = None,
                 user_id: Optional[int] = None, config: Optional[RuntimeConfig] = None):
        self.db = db
        self.loader = AgentLoader(db)
        self.model_name = model_name
        self.user_id = user_id or 1
        self.config = config or RuntimeConfig()
        self._checkpointer = None  # 惰性初始化（断点持久化）

    def _get_checkpointer(self):
        """惰性创建数据库 checkpointer（断点/会话恢复，Harness 运行时增强）。"""
        if self._checkpointer is None:
            try:
                from packages.agent.runtime.checkpointer import create_async_checkpointer
                self._checkpointer = create_async_checkpointer()
            except Exception as e:
                logger.warning("[Orchestrator] checkpointer 初始化失败: %s", e)
                self._checkpointer = None
        return self._checkpointer

    # ---------------- 通用执行 API（运行时完整性：原 AgentRuntime 并入）----------------
    def _build_config(self, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None) -> dict:
        """构建 LangGraph 配置：thread_id/递归上限/checkpointer/中断/回调。"""
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.config.recursion_limit,
        }
        if run_id:
            config["configurable"]["run_id"] = run_id
        checkpointer = self._get_checkpointer()
        if checkpointer and self.config.checkpointer != "none":
            config["configurable"]["checkpoint_saver"] = checkpointer
        if self.config.interrupt_before:
            config["interrupt_before"] = self.config.interrupt_before
        if self.config.interrupt_after:
            config["interrupt_after"] = self.config.interrupt_after
        if callbacks:
            config["callbacks"] = callbacks
        return config

    @property
    def _compressor(self):
        from packages.agent.runtime.context import ContextCompressor
        return ContextCompressor(
            max_tokens=self.config.token_budget,
            reserve_tokens=self.config.reserve_tokens,
        )

    def _prepare_state(self, state: dict) -> dict:
        """执行前用 Token 预算压缩超预算 messages（运行时上下文管理）。"""
        messages = state.get("messages")
        if not messages:
            return state
        compressor = self._compressor
        if not compressor.should_compress(messages):
            return state
        compressed = compressor.compress(messages)
        if len(compressed) != len(messages):
            logger.info("上下文压缩 | %d -> %d 条消息", len(messages), len(compressed))
            return {**state, "messages": compressed}
        return state

    def _retry_policy(self):
        from packages.agent.runtime.retry import RetryPolicy
        return RetryPolicy(
            max_retries=self.config.max_retries,
            delay_seconds=self.config.retry_delay_seconds,
        )

    async def execute(self, graph, state: dict, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None) -> ExecutionResult:
        """批量执行给定编译图：上下文压缩 + 重试 + 硬超时。"""
        from packages.agent.runtime.retry import with_retry
        start = datetime.utcnow()
        run_id = run_id or str(uuid4())
        prepared = self._prepare_state(state)
        config = self._build_config(thread_id, run_id, callbacks)
        policy = self._retry_policy()
        async def _run():
            return await graph.ainvoke(prepared, config=config)
        try:
            result = await asyncio.wait_for(with_retry(_run, policy), timeout=self.config.timeout_seconds)
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            return ExecutionResult.ok(result, duration, {"run_id": run_id})
        except asyncio.TimeoutError:
            return ExecutionResult.error(
                f"执行超时（>{self.config.timeout_seconds}s）",
                int((datetime.utcnow() - start).total_seconds() * 1000),
                metadata={"run_id": run_id, "timeout": True})
        except Exception as e:
            logger.exception("图执行失败 | run=%s", run_id)
            # 保留原始异常（审批 GraphInterrupt 等由此提取）
            return ExecutionResult.error(
                str(e), int((datetime.utcnow() - start).total_seconds() * 1000),
                error=e, metadata={"run_id": run_id})

    async def execute_stream(self, graph, state: dict, thread_id: str, run_id: Optional[str] = None,
                             stream_mode: str = "messages", callbacks: Optional[list] = None):
        """流式执行给定编译图（事件契约：token/complete/error）。"""
        run_id = run_id or str(uuid4())
        config = self._build_config(thread_id, run_id, callbacks)
        try:
            async for event in graph.astream(state, config=config, stream_mode=stream_mode):
                yield self._format_execution_event(event, run_id)
            yield {"type": "complete", "run_id": run_id}
        except Exception as e:
            logger.exception("流式执行失败 | run=%s", run_id)
            yield {"type": "error", "run_id": run_id, "error": str(e)}

    @staticmethod
    def _format_execution_event(event, run_id: str) -> dict:
        from langchain_core.messages import BaseMessage, AIMessage
        if isinstance(event, AIMessage):
            return {"type": "token", "run_id": run_id, "content": event.content or ""}
        if isinstance(event, BaseMessage):
            return {"type": "token", "run_id": run_id, "content": getattr(event, "content", str(event)) or ""}
        if isinstance(event, dict):
            return {"type": event.get("type", "unknown"), "run_id": run_id, **event}
        if hasattr(event, "type"):
            return {"type": event.type, "run_id": run_id, "data": event}
        return {"type": "token", "run_id": run_id, "content": str(event)}

    async def get_state(self, graph, thread_id: str) -> Optional[dict]:
        """状态快照（时间旅行）。"""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await graph.aget_state(config)
            return state.values if state else None
        except Exception as e:
            logger.error("获取状态失败 | thread=%s error=%s", thread_id, e)
            return None

    async def patch_state(self, graph, thread_id: str, values: dict) -> bool:
        """修补状态（时间旅行修改）。"""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            await graph.aupdate_state(config, values)
            return True
        except Exception as e:
            logger.error("修补状态失败 | thread=%s error=%s", thread_id, e)
            return False

    async def resume(self, graph, thread_id: str, values: dict, run_id: Optional[str] = None) -> ExecutionResult:
        """恢复中断执行。"""
        from packages.agent.runtime.retry import with_retry
        start = datetime.utcnow()
        run_id = run_id or str(uuid4())
        config = self._build_config(thread_id, run_id)
        policy = self._retry_policy()
        async def _run():
            return await graph.ainvoke(values, config=config)
        try:
            result = await asyncio.wait_for(with_retry(_run, policy), timeout=self.config.timeout_seconds)
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            return ExecutionResult.ok(result, duration, {"run_id": run_id, "resumed": True})
        except Exception as e:
            return ExecutionResult.error(str(e), int((datetime.utcnow() - start).total_seconds() * 1000))

    def interrupt(self, thread_id: str, run_id: Optional[str] = None) -> bool:
        """请求中断（埋点；实际中断由 LangGraph 中断机制完成）。"""
        logger.info("中断请求 | thread=%s run=%s", thread_id, run_id)
        return True

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

        sub_security = {}
        if cfg.tools_whitelist:
            sub_security["allowed_tools"] = cfg.tools_whitelist
        if cfg.require_approval_tools:
            sub_security["require_approval_tools"] = cfg.require_approval_tools

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
            content = self._extract_final_content(result.get("messages", []))
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

        model_name = self.model_name or "qwen3.5-397b-a17b"
        config = ModelConfig(
            provider=model_name,  # 会作为 model_id 反查真实 provider
            model=model_name,
            temperature=0.3,
            max_tokens=2048,
        )
        return await create_langchain_llm(config, self.db)

    # ---------------- 主编排节点 ----------------
    async def _orchestrate(self, llm: Any, messages: List[Dict[str, str]],
                           main_prompt: str, catalog: List[Dict[str, str]]) -> OrchestrationPlan:
        from langchain_core.messages import HumanMessage, SystemMessage

        # 注入子 Agent 目录，让主 Agent 从候选中选择（而非记忆 UUID）
        if catalog:
            catalog_text = "\n".join(
                f"- agent_id: {e['agent_id']}, name: {e['name']}, 用途: {e.get('description') or ''}"
                for e in catalog
            )
            catalog_block = f"\n\n可用子 Agent 目录（只能从中选择，agent_id 必须原样输出）：\n{catalog_text}"
        else:
            catalog_block = "\n\n（当前无可用子 Agent，直接回答即可）"

        prompt_msgs = [
            SystemMessage(content=f"{MAIN_ORCHESTRATOR_PROMPT}{catalog_block}\n\n你的身份：{main_prompt}")
        ]
        prompt_msgs.append(HumanMessage(content=messages[-1]["content"] if messages else ""))

        resp = await llm.ainvoke(prompt_msgs)
        return self._parse_plan(resp.content)

    @staticmethod
    def _parse_plan(content: Any) -> OrchestrationPlan:
        text = content if isinstance(content, str) else str(content)
        try:
            data = json.loads(text)
        except Exception as e:
            logger.warning("主 Agent plan 解析失败，按无需子 Agent 处理: %s", e)
            return OrchestrationPlan(need_sub_agents=False, plan=[], run_mode="serial",
                                     direct_answer=text[:500])
        return OrchestrationPlan.model_validate(
            {
                "need_sub_agents": bool(data.get("need_sub_agents")),
                "run_mode": data.get("run_mode", "serial"),
                "plan": data.get("plan") or [],
                "direct_answer": data.get("direct_answer"),
            }
        )

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

    # ---------------- middleware 装配 ----------------
    def _build_middlewares(self, security_policy: Optional[dict] = None) -> List[Any]:
        """装配 harness 管控中间件（与单 Agent 路径一致，实现全链路管控）。

        复用 middlewares/builtin 的四个中间件（日志/审计/安全/上下文）。
        """
        from packages.agent.middlewares.builtin import (
            AuditLoggerMiddleware,
            ContextInitMiddleware,
            SecurityGuardMiddleware,
            ToolLoggingMiddleware,
        )
        return [
            ContextInitMiddleware(),
            ToolLoggingMiddleware(),
            AuditLoggerMiddleware(),
            SecurityGuardMiddleware(policy=security_policy or {}),
        ]

    # ---------------- 统一图构建（单一内核）----------------
    def _build_agent_graph(self, llm: Any, tools: Optional[List[Any]] = None,
                           system_prompt: Optional[str] = None, max_iterations: int = 10,
                           on_token: Optional[Any] = None,
                           security_policy: Optional[dict] = None,
                           checkpointer: Optional[Any] = None,
                           use_checkpointer: bool = False,
                           agent_config: Optional[dict] = None,
                           sandbox_workdir: Optional[str] = None):
        """统一构建 TAO Graph：middleware + 权限引擎 + 输出治理 + checkpointer + Harness 上下文工程。

        集成 Harness 上下文工程子系统（设计文档 2.1）：
        - PromptAssembler：SOUL/CLAUDE 分层提示词组装
        - TokenBudgetManager：Token 预算控制

        主/子 Agent 执行默认不启用 checkpointer（即时任务；
        DatabaseCheckpointSaver 尚未实现 LangChain 消息的特殊序列化，工具调用会产生
        含 HumanMessage 的复杂状态而触发 JSONB 序列化错误）。断点持久化待其序列化修复后恢复。
        """
        from packages.agent.output.governance import OutputGovernanceNode
        from packages.agent.runtime_engine.permission import PermissionEngine
        from packages.agent.core.harness.context import PromptAssembler

        # Harness 上下文工程：使用 PromptAssembler 组装系统提示词（设计文档 11.4）
        prompt_assembler = None
        if agent_config:
            soul = agent_config.get("soul", "")
            claude = agent_config.get("claude", "")
            token_budget = agent_config.get("token_budget", 8192)
            prompt_assembler = PromptAssembler(
                system_prompt="\n\n".join(filter(None, [soul, claude])) or system_prompt,
                max_tokens=token_budget,
                reserve_tokens=512,
            )
        elif system_prompt:
            prompt_assembler = PromptAssembler(
                system_prompt=system_prompt,
                max_tokens=8192,
                reserve_tokens=512,
            )

        # 权限引擎（Harness 管控层：工具白名单/审批/拒绝）
        permission_engine = None
        if security_policy:
            try:
                permission_engine = PermissionEngine(db=self.db, user_id=self.user_id, policy=security_policy)
            except Exception as e:
                logger.warning("[Orchestrator] 权限引擎初始化失败: %s", e)

        middlewares = self._build_middlewares(security_policy)
        output_gov = OutputGovernanceNode(llm=llm, enable_structured=False)
        checkpointer = checkpointer if use_checkpointer else None

        # Harness 工具治理门面（设计文档 2.2）：Phase 0 透传不接管，Phase 1 路由工具执行
        # security_policy 注入门面，使工具级护栏强制白名单（纵深防御，与 permission_check 节点双层）。
        from packages.agent.core.harness.tools import ToolExecutionManager
        execution_manager = ToolExecutionManager(
            db=self.db, user_id=self.user_id, session_id=getattr(self, "session_id", None),
            sandbox_workdir=sandbox_workdir, security_policy=security_policy,
        )

        return build_tao_graph(
            llm=llm,
            tools=tools or [],
            system_prompt=system_prompt or "你是助手。",
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            enable_output_governance=True,
            output_governance_node=output_gov,
            on_token=on_token,
            checkpointer=checkpointer,
            middlewares=middlewares,
            prompt_assembler=prompt_assembler,
            execution_manager=execution_manager,
        )

    @staticmethod
    def _maybe_compress(text: Optional[str], budget: int = 12000) -> Optional[str]:
        """上下文压缩保护：超长输入截断到预算内（ContextCompressor 兜底）。

        多轮历史压缩由 runtime/context.py 的 ContextCompressor 提供；
        此处对超长 system/输入做硬保护。
        """
        if not text or len(text) <= budget:
            return text
        try:
            return text[:budget]
        except Exception:
            return text[:budget]

    @staticmethod
    def _make_pii_redactor():
        """流式 PII 脱敏器（滑动窗口；不可用时降级恒等）。"""
        try:
            from packages.agent.output.filters import PIIFilter
            pii = PIIFilter()
        except Exception as e:
            logger.warning("[Orchestrator] PII 脱敏不可用: %s", e)
            return None

        class _R:
            def __init__(self, window: int = 40):
                self.buf = ""
                self.window = window
            def push(self, text: str) -> str:
                if not text:
                    return ""
                self.buf += text
                if len(self.buf) > self.window:
                    safe, self.buf = self.buf[:-self.window], self.buf[-self.window:]
                    return pii.check(safe)[0]
                return ""
            def flush(self) -> str:
                if not self.buf:
                    return ""
                out = pii.check(self.buf)[0]
                self.buf = ""
                return out
        return _R()

    @staticmethod
    def _redact_block(redactor, text) -> str:
        """一次性把完整文本块脱敏（push 处理主体 + flush 收尾缓冲）。"""
        if redactor is None or not text:
            return str(text) if text is not None else ""
        return redactor.push(str(text)) + redactor.flush()

    # ---------------- 会话保存（记忆/Harness 5 大核心-记忆）----------------
    async def _save_conversation(self, user_id: int, session_id: Optional[str],
                                 query: str, final_output: str,
                                 agent_id: Optional[str] = None) -> None:
        """持久化一轮用户会话到 conversations 表（会话记忆）。"""
        if not session_id:
            return
        try:
            from packages.agent.services.conversation_service import (
                create_or_update_conversation_from_agent,
            )
            await create_or_update_conversation_from_agent(
                db=self.db,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
                messages=[
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": final_output or ""},
                ],
            )
        except Exception as e:
            logger.warning("[Orchestrator] 会话保存失败: %s", e)
            await self.db.rollback()

    async def _load_conversation_history(self, user_id: int, session_id: Optional[str],
                                         limit: int = 6) -> List[Any]:
        """读取会话历史（记忆回灌，Phase 4）：返回 LangChain 消息序列（旧→新）。

        通过 metadata_json.session_id 定位会话（与 _save_conversation 写入约定一致），
        仅取最近 N 轮，超长由 think 节点的 PromptAssembler 做 Token 预算压缩。
        """
        if not session_id:
            return []
        import json as _json
        from sqlalchemy import select
        from langchain_core.messages import HumanMessage, AIMessage
        from packages.agent.models.conversation import Conversation, ConversationMessage
        try:
            convs = (
                await self.db.execute(
                    select(Conversation)
                    .where(Conversation.user_id == user_id, Conversation.is_active.is_(True))
                    .order_by(Conversation.last_message_at.desc())
                    .limit(50)
                )
            ).scalars().all()
            target = None
            for c in convs:
                if not c.metadata_json:
                    continue
                try:
                    if (_json.loads(c.metadata_json) or {}).get("session_id") == session_id:
                        target = c
                        break
                except Exception:
                    continue
            if target is None:
                return []
            msgs = (
                await self.db.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == target.id)
                    .order_by(ConversationMessage.message_index.asc())
                    .limit(limit)
                )
            ).scalars().all()
            out: List[Any] = []
            for m in msgs:
                if m.role == "user":
                    out.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    out.append(AIMessage(content=m.content))
            return out[-limit:]
        except Exception as e:
            logger.warning("[Orchestrator] 会话历史读取失败: %s", e)
            return []

    # ---------------- 执行追踪 ----------------
    async def _save_execution_trace(self, run_id: str, query: str, intent: str,
                                    final_output: str, sub_agents: List[str], user_id: int,
                                    sub_results: Optional[List[Dict]] = None) -> None:
        """记录一次执行追踪（Harness 可观测性）。

        sub_results（#8）：每条子 Agent 独立审计条目（id/success/content 摘要/
        error/approvals 数/thread_id），而非只记 id 列表。
        """
        try:
            from packages.agent.models.execution_trace import ExecutionTrace
            sub_entries = []
            for r in (sub_results or []):
                sub_entries.append({
                    "sub_agent_id": r.get("sub_agent_id"),
                    "success": bool(r.get("success")),
                    "content_summary": str(r.get("content") or "")[:300],
                    "error": r.get("error"),
                    "approval_count": len(r.get("approvals") or []),
                    "thread_id": (r.get("approvals") or [{}])[0].get("thread_id")
                    if r.get("approvals") else None,
                })
            trace = ExecutionTrace(
                run_id=run_id,
                thread_id=run_id,
                user_id=user_id,
                tenant_id=None,
                agent_id=None,
                agent_name="main_agent",
                agent_type="main_agent",
                intent_type=intent,
                status="success" if final_output else "failed",
                latency_ms=0,
                steps=[{
                    "intent": intent,
                    "sub_agents": sub_agents,
                    "sub_agent_results": sub_entries,
                }],
                input_summary=query[:500] if query else None,
                output_summary=str(final_output)[:500] if final_output else None,
            )
            self.db.add(trace)
            await self.db.commit()
        except Exception as e:
            logger.warning("[Orchestrator] 执行追踪保存失败: %s", e)
            await self.db.rollback()

    # ---------------- 子 Agent 执行（ReAct 循环）---------------
    async def _exec_sub_task(self, llm: Any, sub_task: SubTask, main_prompt: str,
                             state: Optional[Dict[str, Any]] = None,
                             history: Optional[List[Any]] = None) -> SubAgentResult:
        """执行单个子 Agent 任务。

        state（OrchestratorState）可选传入：进入时写入 temp_sub_config、退出时清空，
        让统一 State 真正承载"子临时配置"生命周期（Phase 4 #1）。不传则保持函数式局部（兼容旧调用）。
        history（记忆回灌，#5）：inherit_main_context=True 时把会话历史并入子任务提示。
        """
        # 子 Agent 统一走 build_tao_graph（自带 middleware + 权限 + 工具循环 + 输出治理）
        try:
            cfg = await self.loader.load_sub_agent(sub_task.sub_agent_id)
        except Exception as e:
            return SubAgentResult(sub_agent_id=sub_task.sub_agent_id, success=False, error=f"子Agent加载失败: {e}")

        # 统一 State：子图进入填 temp_sub_config（Phase 4 #1）
        if state is not None:
            state["temp_sub_config"] = {
                "agent_id": cfg.agent_id, "name": cfg.name,
                "system_prompt": cfg.system_prompt,
                "tools_whitelist": list(cfg.tools_whitelist), "max_step": cfg.max_step,
            }

        try:
            # 子 Agent 独立 LLM（避免污染主 LLM），按白名单绑定工具
            sub_llm = await self._create_llm()
            tools = self._load_sub_tools(cfg.tools_whitelist)
            if tools:
                try:
                    sub_llm = sub_llm.bind_tools(tools)
                    logger.info("[Orchestrator] 子Agent=%s 绑定工具 %d 个", cfg.name, len(tools))
                except Exception as e:
                    logger.warning("[Orchestrator] 子Agent=%s 工具绑定失败，走纯 LLM: %s", cfg.name, e)

            # 主上下文继承（Phase 3）+ 记忆回灌（#5）：inherit_main_context=true 时
            # 注入主上下文与会话历史到子任务提示
            task_prompt = sub_task.task_prompt
            if cfg.inherit_main_context and main_prompt:
                hist_text = ""
                if history:
                    hist_text = "\n".join(
                        f"{getattr(m, 'type', 'message')}: {getattr(m, 'content', '')}"
                        for m in history
                    )
                    hist_text = f"\n[会话历史]\n{hist_text}\n"
                task_prompt = f"{main_prompt}{hist_text}\n\n[子任务]\n{task_prompt}"

            sub_system = cfg.system_prompt or "你是专业子 Agent，请用工具（如需要）完成任务。"
            # 统一经 _build_agent_graph（middleware + 输出治理 + 权限全装配）
            # 传入安全策略（allowed + require_approval）以启用人工审批
            sub_security = {}
            if cfg.tools_whitelist:
                sub_security["allowed_tools"] = cfg.tools_whitelist
            if cfg.require_approval_tools:
                sub_security["require_approval_tools"] = cfg.require_approval_tools

            # 按 sandbox_policy 初始化独立沙箱生命周期（Phase 3）：进入创建、退出销毁
            if cfg.sandbox_policy:
                from packages.agent.harness.sandbox.runtime import SandboxScope
                async with SandboxScope(
                    db=self.db, user_id=self.user_id,
                    session_id=getattr(self, "session_id", None), policy=cfg.sandbox_policy,
                ) as scope:
                    return await self._run_sub_agent_graph(
                        sub_llm, tools, sub_system, sub_security, cfg, task_prompt,
                        sandbox_workdir=scope.workdir,
                    )
            return await self._run_sub_agent_graph(
                sub_llm, tools, sub_system, sub_security, cfg, task_prompt,
                sandbox_workdir=None,
            )
        finally:
            # 统一 State：子图退出清空 temp_sub_config（Phase 4 #1）
            if state is not None:
                state["temp_sub_config"] = None

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
        content = self._extract_final_content(state.get("messages", []))
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
        except Exception:
            pass
        return []

    @staticmethod
    def _extract_final_content(messages: list) -> str:
        """从 TAO 图结果中提取最终 AI 回答内容。"""
        content = ""
        for m in messages:
            if getattr(m, "type", "") in ("ai", "assistant"):
                c = getattr(m, "content", "") or ""
                if c:
                    content = str(c)
        return content

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
        redactor = self._make_pii_redactor()
        q: asyncio.Queue = asyncio.Queue()

        async def on_token(chunk):
            q.put_nowait(chunk)

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
            from packages.agent.harness.sandbox.runtime import SandboxScope
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
            sandbox_workdir=sandbox_workdir,
        )

        def _redact(text: str) -> str:
            if redactor is None or not text:
                return text
            return redactor.push(text)

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
                    chunk = await asyncio.wait_for(q.get(), timeout=0.1)
                    c = _redact(getattr(chunk, "content", "") or "")
                    if c:
                        yield c
                except asyncio.TimeoutError:
                    if gtask.done():
                        if not gtask.cancelled() and gtask.exception() is not None and \
                                not isinstance(gtask.exception(), asyncio.CancelledError):
                            logger.warning("[Orchestrator] 直答图执行结束（含异常）: %s", gtask.exception())
                        while not q.empty():
                            chunk = q.get_nowait()
                            c = _redact(getattr(chunk, "content", "") or "")
                            if c:
                                yield c
                        break
                    continue
            if redactor is not None:
                tail = redactor.flush()
                if tail:
                    yield tail
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
            tools=["save_workspace_file"],
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
        """流式聚合：逐 token 产出最终回答（应用 PII 脱敏）。失败时降级为一次性汇总。"""
        from langchain_core.messages import HumanMessage, SystemMessage

        results_text = json.dumps(
            [{"sub_agent_id": r.sub_agent_id, "success": r.success, "content": str(r.content)[:1500], "error": r.error}
             for r in results], ensure_ascii=False)
        prompt = AGGREGATE_PROMPT.replace("{results}", results_text)
        msgs = [SystemMessage(content=main_prompt), HumanMessage(content=prompt)]

        try:
            async for chunk in llm.astream(msgs):
                c = getattr(chunk, "content", "") or ""
                if c:
                    if redactor is not None:
                        c = redactor.push(str(c))
                    if c:
                        yield str(c)
            if redactor is not None:
                tail = redactor.flush()
                if tail:
                    yield tail
        except Exception as e:
            logger.error("[Orchestrator] 流式聚合失败，降级: %s", e)
            parts = [f"【{r.sub_agent_id}】{r.content if r.success else '执行失败: ' + str(r.error)}"
                     for r in results]
            block = "以下为子 Agent 执行结果汇总：\n" + "\n".join(parts)
            yield self._redact_block(redactor, block)

    @staticmethod
    def _chunk_text(text: str, size: int = 2):
        """把一段文本切成小块逐段产出（伪流式打字机）。"""
        for i in range(0, len(text), size):
            yield text[i:i + size]

    # ---------------- 流式统一入口 ----------------
    async def run_stream(
        self,
        query: str,
        main_prompt: Optional[str] = None,
        run_mode: str = "serial",
        user_id: Optional[int] = None,
        allow_sub_agents: bool = True,
        session_id: Optional[str] = None,
    ):
        """主 Agent 统一调度流式入口（async generator）——一切请求由主 Agent 调度。

        产出事件：
        - {"type":"orchestrator_plan","data":{...}}
        - {"type":"sub_agent","data":{sub_agent_id, status:"running"|"done", success?, content?}}
        - {"type":"token","content":...}  聚合/直接回答 的打字机内容

        Args:
            allow_sub_agents: 是否允许主 Agent 派生子 Agent（False 时仅直接回答）
        """
        from packages.agent.orchestrator.business_tools import ensure_business_tools
        from packages.agent.orchestrator.supervisor import build_supervisor_graph

        # 兜底：允许调用方经 run_stream(user_id=...) 传入真实身份，
        # 使会话/追踪/thread_id/权限引擎都归属当前用户（而非构造时的默认值）
        if user_id is not None:
            self.user_id = user_id

        # 主 Agent 配置化（Phase 2）：本地文件 soul/claude/agent.yaml 驱动；
        # API 显式传入 main_prompt 时作覆盖（兜底保持兼容）。
        main_agent_cfg = self.loader.load_main_agent(
            system_prompt=main_prompt or None,
            tools=["save_workspace_file"],
        )
        main_prompt = main_agent_cfg.system_prompt or "你是通用助手，可协调多个子 Agent 完成任务。"
        redactor = self._make_pii_redactor()

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
                            ev = sink.get_nowait()
                            if ev is not None:
                                yield ev
                        if exc is not None:
                            logger.warning("[Orchestrator] 编排图异常: %s", exc)
                        break
                    continue
                if ev is not None:
                    yield ev
        finally:
            if not gtask.done():
                gtask.cancel()

        # 图完成后取终态做副作用（会话记忆 + 追踪）
        try:
            final_state = gtask.result()
        except Exception:
            final_state = state
        self._last_orchestrator_state = dict(final_state)
        final_answer = (final_state.get("final_answer") or "")[:500]
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
