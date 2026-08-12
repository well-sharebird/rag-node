"""主编排图 - 主 Agent 编排 + 子 Agent 子图执行 + 聚合

MVP 采用可稳定落地的实现：
- 主 Agent 决策：LLM 输出 JSON plan（need_sub_agents / run_mode / plan / direct_answer），解析为结构
- 子 Agent：复用 build_tao_graph 执行（含工具能力），支持串行 / 并行
- 聚合：主 Agent 读取全部子结果生成最终回答
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.orchestrator.agent_loader import AgentLoader
from packages.agent.orchestrator.state import (
    OrchestrationPlan,
    SubAgentResult,
    SubTask,
)
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

    def __init__(self, db: AsyncSession, model_name: Optional[str] = None, user_id: Optional[int] = None):
        self.db = db
        self.loader = AgentLoader(db)
        self.model_name = model_name
        self.user_id = user_id or 1
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
                           agent_config: Optional[dict] = None):
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

    # ---------------- 执行追踪 ----------------
    async def _save_execution_trace(self, run_id: str, query: str, intent: str,
                                    final_output: str, sub_agents: List[str], user_id: int) -> None:
        """记录一次执行追踪（Harness 可观测性）。"""
        try:
            from packages.agent.models.execution_trace import ExecutionTrace
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
                steps=[{"intent": intent, "sub_agents": sub_agents}],
                input_summary=query[:500] if query else None,
                output_summary=str(final_output)[:500] if final_output else None,
            )
            self.db.add(trace)
            await self.db.commit()
        except Exception as e:
            logger.warning("[Orchestrator] 执行追踪保存失败: %s", e)
            await self.db.rollback()

    # ---------------- 子 Agent 执行（ReAct 循环）---------------
    async def _exec_sub_task(self, llm: Any, sub_task: SubTask, main_prompt: str) -> SubAgentResult:
        # 子 Agent 统一走 build_tao_graph（自带 middleware + 权限 + 工具循环 + 输出治理）
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            cfg = await self.loader.load_sub_agent(sub_task.sub_agent_id)
        except Exception as e:
            return SubAgentResult(sub_agent_id=sub_task.sub_agent_id, success=False, error=f"子Agent加载失败: {e}")

        # 子 Agent 独立 LLM（避免污染主 LLM），按白名单绑定工具
        sub_llm = await self._create_llm()
        tools = self._load_sub_tools(cfg.tools_whitelist)
        if tools:
            try:
                sub_llm = sub_llm.bind_tools(tools)
                logger.info("[Orchestrator] 子Agent=%s 绑定工具 %d 个", cfg.name, len(tools))
            except Exception as e:
                logger.warning("[Orchestrator] 子Agent=%s 工具绑定失败，走纯 LLM: %s", cfg.name, e)

        sub_system = cfg.system_prompt or "你是专业子 Agent，请用工具（如需要）完成任务。"
        # 统一经 _build_agent_graph（middleware + 输出治理 + 权限全装配）
        # 传入安全策略（allowed + require_approval）以启用人工审批
        sub_security = {}
        if cfg.tools_whitelist:
            sub_security["allowed_tools"] = cfg.tools_whitelist
        if cfg.require_approval_tools:
            sub_security["require_approval_tools"] = cfg.require_approval_tools
        graph = self._build_agent_graph(
            llm=sub_llm,
            tools=tools,
            system_prompt=sub_system,
            max_iterations=max(1, cfg.max_step),
            security_policy=sub_security or None,
        )

        try:
            state = await graph.ainvoke(
                {"messages": [HumanMessage(content=sub_task.task_prompt)]},
                config={"configurable": {"thread_id": f"{self.user_id}:main:{int(__import__('time').time() * 1000)}"}},
            )
            # 人工审批：敏感工具 require_approval 产生 __interrupt__ → 提取审批请求
            approvals = self._extract_approvals(state)
            if approvals:
                return SubAgentResult(
                    sub_agent_id=sub_task.sub_agent_id, success=True,
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
            return SubAgentResult(sub_agent_id=sub_task.sub_agent_id, success=True, content=content)
        except Exception as e:
            # 兼容 LangGraph GraphInterrupt 抛出场景
            approvals = self._extract_approvals(e)
            if approvals:
                return SubAgentResult(
                    sub_agent_id=sub_task.sub_agent_id, success=True,
                    content="[需要审批] 敏感工具调用已发起审批请求，等待批准后可重试。",
                    approvals=approvals,
                )
            logger.exception("[Orchestrator] 子 Agent 执行失败: %s", sub_task.sub_agent_id)
            return SubAgentResult(sub_agent_id=sub_task.sub_agent_id, success=False, error=str(e))

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
    async def _direct_answer_stream(self, query: str, main_prompt: str):
        """主 Agent 直接回答：经统一图（含 middleware + PII 脱敏）流式输出。"""
        from langchain_core.messages import HumanMessage

        main_llm = await self._create_llm()
        redactor = self._make_pii_redactor()
        q: asyncio.Queue = asyncio.Queue()

        async def on_token(chunk):
            q.put_nowait(chunk)

        graph = self._build_agent_graph(
            llm=main_llm,
            tools=[],  # 直接回答纯问答；需要能力时由主 Agent 派发子 Agent
            system_prompt=main_prompt or "你是通用助手。",
            max_iterations=10,
            on_token=on_token,
        )

        def _redact(text: str) -> str:
            if redactor is None or not text:
                return text
            return redactor.push(text)

        gtask = asyncio.create_task(
            graph.ainvoke(
                {"messages": [HumanMessage(content=query)]},
                config={"configurable": {"thread_id": f"{self.user_id}:main:{int(__import__('time').time() * 1000)}"}},
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

    # ---------------- 聚合节点 ----------------
    async def _aggregate(self, llm: Any, results: List[SubAgentResult], main_prompt: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        results_text = json.dumps(
            [{"sub_agent_id": r.sub_agent_id, "success": r.success, "content": str(r.content)[:1500], "error": r.error}
             for r in results], ensure_ascii=False)
        # 用 replace 而非 format：避免结果 JSON 中的 {} 被 str.format 误解析
        prompt = AGGREGATE_PROMPT.replace("{results}", results_text)
        # system 保持轻量（仅主身份），结果放 Human 消息，规避大 system 内容导致的 400
        msgs = [SystemMessage(content=main_prompt), HumanMessage(content=prompt)]
        try:
            resp = await llm.ainvoke(msgs)
            return str(getattr(resp, "content", ""))
        except Exception as e:
            _body = getattr(e, "response", None)
            _eb = _body.text if _body is not None else str(e)
            logger.error("[Orchestrator] 聚合失败: %s | body=%s", e, _eb)
            # 降级：拼装各子 Agent 结果，不弹 500
            parts = [f"【{r.sub_agent_id}】{r.content if r.success else '执行失败: ' + str(r.error)}"
                     for r in results]
            return "以下为子 Agent 执行结果汇总：\n" + "\n".join(parts)

    # ---------------- 统一入口 ----------------
    async def run(
        self,
        query: str,
        main_prompt: Optional[str] = None,
        run_mode: str = "serial",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行一次主从编排。返回 {final_answer, sub_tasks, sub_agent_results}。"""
        llm = await self._create_llm()
        main_prompt = main_prompt or "你是通用助手，可协调多个子 Agent 完成任务。"

        # 0. 注册业务工具（供子 Agent 白名单绑定），并加载子 Agent 目录
        from packages.agent.orchestrator.business_tools import ensure_business_tools
        try:
            await ensure_business_tools(self.db, user_id=self.user_id)
        except Exception as e:
            logger.warning("[Orchestrator] 业务工具注册失败，继续: %s", e)
        catalog = await self.loader.list_sub_agents(user_id)

        # 1. 主编排决策（注入目录）
        plan = await self._orchestrate(llm, [{"role": "user", "content": query}], main_prompt, catalog)

        # 2. 无需子 Agent → 直接回答
        if not plan.need_sub_agents or not plan.plan:
            return {
                "final_answer": plan.direct_answer or "",
                "sub_tasks": [],
                "sub_agent_results": [],
            }

        # 3. 解析并校验目录中的 sub_agent_id（LLM 可能输出名称/错误 id → 映射回真实 id）
        resolved = []
        for t in plan.plan:
            real_id = self.loader.resolve_sub_agent_id(
                getattr(t, "sub_agent_id", ""), catalog
            )
            resolved.append(SubTask(sub_agent_id=real_id or t.sub_agent_id, task_prompt=t.task_prompt))
        sub_tasks = resolved
        mode = plan.run_mode or run_mode

        if mode == "parallel":
            results = await asyncio.gather(
                *[self._exec_sub_task(llm, t, main_prompt) for t in sub_tasks]
            )
        else:
            results = []
            for t in sub_tasks:
                results.append(await self._exec_sub_task(llm, t, main_prompt))

        # 4. 聚合
        final = await self._aggregate(llm, results, main_prompt)

        return {
            "final_answer": final,
            "sub_tasks": [t.model_dump() for t in sub_tasks],
            "sub_agent_results": [r.model_dump() for r in results],
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
        from packages.agent.tools.registry import get_tool_registry

        # 兜底：允许调用方经 run_stream(user_id=...) 传入真实身份，
        # 使会话/追踪/thread_id/权限引擎都归属当前用户（而非构造时的默认值）
        if user_id is not None:
            self.user_id = user_id

        llm = await self._create_llm()
        main_prompt = main_prompt or "你是通用助手，可协调多个子 Agent 完成任务。"
        redactor = self._make_pii_redactor()

        try:
            await ensure_business_tools(self.db, user_id=self.user_id)
        except Exception as e:
            logger.warning("[Orchestrator] 业务工具注册失败，继续: %s", e)
        catalog = await self.loader.list_sub_agents(user_id)

        # 1. 主编排决策（统一由主 Agent 调度；若不允许派子则强制直接回答）
        plan = await self._orchestrate(llm, [{"role": "user", "content": query}], main_prompt, catalog)
        if not allow_sub_agents:
            plan.need_sub_agents = False
            plan.plan = []
        yield {
            "type": "orchestrator_plan",
            "data": {
                "need_sub_agents": plan.need_sub_agents,
                "run_mode": plan.run_mode,
                "plan": [t.model_dump() for t in plan.plan],
            },
        }

        # 2. 无需子 Agent → 主 Agent 直接回答（走 tao_graph，middleware + PII 全装配 + 流式）
        if not plan.need_sub_agents or not plan.plan:
            collected = []
            async for tok in self._direct_answer_stream(query, main_prompt):
                collected.append(tok)
                yield {"type": "token", "content": tok}
            final_answer = "".join(collected)
            # 会话记忆 + 执行追踪
            await self._save_conversation(user_id=self.user_id, session_id=session_id,
                                          query=query, final_output=final_answer[:500])
            try:
                run_id = f"run_{int(__import__('time').time() * 1000)}"
                await self._save_execution_trace(
                    run_id=run_id, query=query, intent="direct_answer",
                    final_output=final_answer[:500], sub_agents=[], user_id=self.user_id,
                )
            except Exception as e:
                logger.warning("[Orchestrator] 追踪保存异常: %s", e)
            return

        # 3. 解析并校验子 Agent id
        sub_tasks = [
            SubTask(
                sub_agent_id=self.loader.resolve_sub_agent_id(getattr(t, "sub_agent_id", ""), catalog) or t.sub_agent_id,
                task_prompt=t.task_prompt,
            )
            for t in plan.plan
        ]
        mode = plan.run_mode or run_mode

        # 4. 执行子任务（事件反馈；敏感工具审批 → approval_required 事件）
        results: List[SubAgentResult] = []

        def _emit_events(t, r) -> List[dict]:
            """子 Agent 结果 → 事件列表（含审批需求 → approval_required；内容统一脱敏）。"""
            evs = []
            if getattr(r, "approvals", None):
                evs.append({"type": "approval_required", "data": {
                    "sub_agent_id": t.sub_agent_id, "pending": r.approvals}})
            evs.append({"type": "sub_agent", "data": {
                "sub_agent_id": t.sub_agent_id, "status": "done",
                "success": r.success, "content": self._redact_block(redactor, r.content)}})
            return evs

        if mode == "parallel":
            results = await asyncio.gather(
                *[self._exec_sub_task(llm, t, main_prompt) for t in sub_tasks]
            )
            for t, r in zip(sub_tasks, results):
                for ev in _emit_events(t, r):
                    yield ev
        else:
            for t in sub_tasks:
                yield {"type": "sub_agent", "data": {"sub_agent_id": t.sub_agent_id, "status": "running"}}
                r = await self._exec_sub_task(llm, t, main_prompt)
                results.append(r)
                for ev in _emit_events(t, r):
                    yield ev

        # 5. 聚合（流式打字机，PII 脱敏）
        final_answer_parts = []
        async for tok in self._aggregate_stream(llm, results, main_prompt, redactor=redactor):
            yield {"type": "token", "content": tok}
            final_answer_parts.append(tok)
        final_answer = "".join(final_answer_parts)

        # 会话记忆：多 Agent 编排结果同样持久化（与直答分支一致）
        await self._save_conversation(user_id=self.user_id, session_id=session_id,
                                      query=query, final_output=final_answer[:500])

        # 6. 执行追踪（Harness 可观测性）
        try:
            run_id = f"run_{int(__import__('time').time() * 1000)}"
            await self._save_execution_trace(
                run_id=run_id, query=query, intent="orchestrator",
                final_output=final_answer[:500], sub_agents=[t.sub_agent_id for t in sub_tasks],
                user_id=self.user_id,
            )
        except Exception as e:
            logger.warning("[Orchestrator] 追踪保存异常: %s", e)
