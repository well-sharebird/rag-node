"""主/子 Agent 编排 supervisor 图（LangGraph 状态机）。

把「主 LLM 出 plan → 按 State 路由直答/子 Agent 调度 → 聚合」从过程式 run_stream
抽成一张真 LangGraph 图，以 OrchestratorState 驱动流转，达成设计铁律
「执行交给 LangGraph、多 Agent 串/并行由子图调度」。

节点为 closure（捕获 runtime 与共享 sink）：
    plan_node →(条件边 router)→ direct_node | dispatch_node → aggregate_node → END

- sink：共享事件队列（asyncio.Queue 或 NoopSink）。节点用 put_nowait 产出
  orchestrator_plan / sub_agent / approval_required / token 事件，run_stream 门面
  drain 该队列实现打字机流式；非流式 run 用 NoopSink。
- 节点只返回变更键（不 echo 全 state），OrchestratorState 默认 overwrite 语义即可。
- 子 Agent 调用复用 runtime._exec_sub_task（内部已含 temp_sub_config 生命周期 + 沙箱 + 审批折成 approvals）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from packages.agent.orchestrator.text_utils import redact_block
from packages.agent.schemas.stream import (
    ev_approval,
    ev_plan,
    ev_reasoning,
    ev_sub_agent,
    ev_token,
)

logger = logging.getLogger(__name__)

# 超时/审批/沙箱等真实治理全部留在子 Agent 执行（_exec_sub_task），
# supervisor 只做状态机调度，不接触 LangGraph interrupt —— 故禁止给本图配 checkpointer/interrupt。


class NoopSink:
    """非流式 sink：丢弃全部事件（run 路径）。"""

    def put_nowait(self, event: Any) -> None:
        return None


def build_supervisor_graph(
    runtime: Any,
    *,
    sink: Any,
    query: str,
    main_prompt: str,
    main_agent_cfg: Any,
    catalog: List[Dict[str, Any]],
    run_mode: str = "serial",
    allow_sub_agents: bool = True,
    session_id: Optional[str] = None,
    redactor: Optional[Any] = None,
    direct_strategy: str = "graph",
    history: Optional[List[Any]] = None,
) -> Any:
    """构建 supervisor 编排图。

    direct_strategy:
        "graph" — direct_node 走完整 _direct_answer_stream（run_stream，含记忆回灌/工具/流式）；
        "quick"  — direct_node 直接返回 plan.direct_answer（run 非流式，保持旧行为）。
    """
    from langgraph.graph import END, START, StateGraph

    from packages.agent.orchestrator.state import (
        OrchestrationPlan,
        OrchestratorState,
        SubAgentResult,
        SubTask,
    )

    ctx: Dict[str, Any] = {"plan": None, "run_mode": run_mode}

    def _emit_events(t: SubTask, r: SubAgentResult) -> List[Dict[str, Any]]:
        """子 Agent 结果 → 事件（审批需求 → approval_required；内容统一脱敏）。"""
        evs: List[Dict[str, Any]] = []
        if getattr(r, "approvals", None):
            evs.append(ev_approval(sub_agent_id=t.sub_agent_id, pending=r.approvals))
        evs.append(ev_sub_agent(
            sub_agent_id=t.sub_agent_id, status="done",
            success=r.success, content=redact_block(redactor, r.content)))
        return evs

    async def plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
        llm = await runtime._create_llm()
        # 记忆回灌（#5）：编排决策也看到会话历史（当前查询置于末尾）
        orchestration_msgs = [
            *([{"role": getattr(m, "type", "user"), "content": getattr(m, "content", "")}
               for m in (history or [])]),
            {"role": "user", "content": query},
        ]
        plan: OrchestrationPlan = await runtime._orchestrate(
            llm, orchestration_msgs, main_prompt, catalog)
        ctx["plan"] = plan
        if not allow_sub_agents:
            plan.need_sub_agents = False
            plan.plan = []
        ctx["run_mode"] = plan.run_mode or run_mode

        tasks: List[SubTask] = []
        for t in plan.plan:
            real_id = runtime.loader.resolve_sub_agent_id(
                getattr(t, "sub_agent_id", ""), catalog) or t.sub_agent_id
            tasks.append(SubTask(sub_agent_id=real_id, task_prompt=t.task_prompt))

        sink.put_nowait(ev_plan(
            need_sub_agents=plan.need_sub_agents,
            run_mode=plan.run_mode,
            plan=[t.model_dump() for t in tasks],
        ))
        return {"sub_tasks": [t.model_dump() for t in tasks]}

    async def direct_node(state: Dict[str, Any]) -> Dict[str, Any]:
        if direct_strategy == "quick":
            text = (ctx["plan"].direct_answer if ctx["plan"] is not None else None) or ""
            return {"final_answer": text[:500] if text else ""}
        collected: List[str] = []
        async for kind, tok in runtime._direct_answer_stream(
                query, main_prompt, main_agent_cfg, session_id=session_id):
            if kind == "reasoning":
                sink.put_nowait(ev_reasoning(content=tok))
            else:
                collected.append(tok)
                sink.put_nowait(ev_token(content=tok))
        final = "".join(collected)
        return {"final_answer": final[:500]}

    async def dispatch_node(state: Dict[str, Any]) -> Dict[str, Any]:
        sub_tasks: List[SubTask] = []
        for raw in state.get("sub_tasks") or []:
            try:
                sub_tasks.append(SubTask(sub_agent_id=raw["sub_agent_id"],
                                         task_prompt=raw.get("task_prompt", "")))
            except Exception as e:
                logger.warning("[Supervisor] 子任务解析跳过: %s", e)

        mode = ctx.get("run_mode") or run_mode
        results: List[SubAgentResult] = []

        # #7：temp_sub_config 生命周期接到真实 OrchestratorState（而非一次性哑元）。
        # _exec_sub_task 进入填 temp_sub_config、退出(finally)清空，终态仍为 None，隔离保持。
        if mode == "parallel":
            gathered = await asyncio.gather(
                *[runtime._exec_sub_task(None, t, main_prompt,
                                         state=state, history=history)
                  for t in sub_tasks]
            )
            for t, r in zip(sub_tasks, gathered):
                results.append(r)
                for ev in _emit_events(t, r):
                    sink.put_nowait(ev)
        else:
            for t in sub_tasks:
                sink.put_nowait(ev_sub_agent(sub_agent_id=t.sub_agent_id, status="running"))
                r = await runtime._exec_sub_task(None, t, main_prompt,
                                                 state=state, history=history)
                results.append(r)
                for ev in _emit_events(t, r):
                    sink.put_nowait(ev)

        return {"sub_agent_results": [r.model_dump() for r in results], "temp_sub_config": None}

    async def aggregate_node(state: Dict[str, Any]) -> Dict[str, Any]:
        results: List[SubAgentResult] = []
        for raw in state.get("sub_agent_results") or []:
            try:
                results.append(SubAgentResult(**raw))
            except Exception as e:
                logger.warning("[Supervisor] 结果解析跳过: %s", e)
        llm = await runtime._create_llm()
        collected: List[str] = []
        async for tok in runtime._aggregate_stream(llm, results, main_prompt, redactor=redactor):
            collected.append(tok)
            sink.put_nowait(ev_token(content=tok))
        final = "".join(collected)
        return {"final_answer": final[:500]}

    async def router(state: Dict[str, Any]) -> str:
        return "direct" if not (state.get("sub_tasks") or []) else "dispatch"

    g = StateGraph(OrchestratorState)
    g.add_node("plan", plan_node)
    g.add_node("direct", direct_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("aggregate", aggregate_node)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", router, {"direct": "direct", "dispatch": "dispatch"})
    g.add_edge("direct", END)
    g.add_edge("dispatch", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()
