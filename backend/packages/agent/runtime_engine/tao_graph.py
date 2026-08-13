"""
TAO Graph - 基于 LangGraph 的思考 - 行动 - 观察循环

将 TAO Loop 从独立循环引擎重构为 LangGraph 的条件边 + 自环图结构

核心设计:
1. Think 节点 - LLM 推理生成行动计划
2. Act 节点 - ToolNode 执行工具
3. Observe 节点 - 处理执行结果
4. 条件边 - 决定是否继续循环
5. 权限检查节点 - 工具执行前权限校验 (可选)
6. 输出治理节点 - 最终输出过滤 (可选)
"""
import logging
from typing import Any, Dict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langgraph.prebuilt import ToolNode

from packages.agent.runtime_engine.state import TAOState

logger = logging.getLogger(__name__)


def build_tao_graph(
    llm: Any,
    tools: List[Any],
    max_iterations: int = 10,
    permission_engine: Optional[Any] = None,
    enable_output_governance: bool = True,
    output_governance_node: Optional[Any] = None,
    system_prompt: Optional[str] = None,
    on_token: Optional[Any] = None,
    checkpointer: Optional[Any] = None,
    middlewares: Optional[List[Any]] = None,
    prompt_assembler: Optional[Any] = None,
    execution_manager: Optional[Any] = None,
) -> CompiledStateGraph:
    """
    构建 TAO 循环图

    Args:
        llm: LLM 实例 (已绑定工具)
        tools: 工具列表
        max_iterations: 最大迭代次数
        permission_engine: 权限引擎 (可选)
        enable_output_governance: 是否启用输出治理
        output_governance_node: 输出治理节点 (可选)
        system_prompt: 系统提示词 (可选)
        on_token: 流式 token 回调 async (chunk: AIMessageChunk) -> None (可选)
        checkpointer: LangGraph checkpointer (编译时注入，启用断点持久化)
        middlewares: LangChain AgentMiddleware 列表（由节点驱动的管控中间件）
        prompt_assembler: PromptAssembler（Harness 层上下文组装器，设计文档 11.4）
        execution_manager: ToolExecutionManager（Harness 工具执行唯一门面，设计文档 2.2）。
            线程注：Phase 0 仅透传不切换，act_node 仍走 ToolRegistry.safe_invoke；
            Phase 1 由此处接管工具执行（按风险分级路由进程内/沙箱）。

    Returns:
        CompiledStateGraph: 编译后的图
    """
    # 中间件链（替换自研 hooks 系统）
    from packages.agent.core.harness.middleware.base import MiddlewareChain
    chain = MiddlewareChain(middlewares)

    graph = StateGraph(TAOState)

    # 1. Think 节点 - LLM 推理 (注入系统提示词)
    # Harness 层通过 PromptAssembler 组装上下文（设计文档 11.4）
    graph.add_node("think", create_think_node(llm, system_prompt, on_token, chain, prompt_assembler))

    # 2. 权限检查节点 (可选；仅当有工具可检查时才有意义)
    has_tools = bool(tools)
    if permission_engine and has_tools:
        graph.add_node("permission_check", create_permission_check_node(permission_engine))

    # 3. Act 节点 - 使用 LangGraph ToolNode
    if has_tools:
        graph.add_node("act", create_act_node(tools, permission_engine, execution_manager))

    # 4. Observe 节点 - 处理结果
    graph.add_node("observe", create_observe_node())

    # 5. 输出治理节点 (可选)
    has_governance = enable_output_governance and output_governance_node
    if has_governance:
        graph.add_node("output_governance", output_governance_node)

    # 6. 条件边 - Think 后决定是 Act 还是结束
    end_target = "output_governance" if has_governance else END
    if permission_engine and has_tools:
        # 有工具：先经权限检查再执行
        graph.add_conditional_edges(
            "think",
            create_should_act_router(max_iterations),
            {"act": "permission_check", "end": end_target},
        )
        graph.add_edge("permission_check", "act")
    else:
        # 无工具或无需权限：直接执行/结束
        graph.add_conditional_edges(
            "think",
            create_should_act_router(max_iterations),
            {"act": "act" if has_tools else END, "end": end_target},
        )

    # 7. Act 后到 Observe
    if has_tools:
        graph.add_edge("act", "observe")
        # 8. Observe 后回到 Think (形成循环)
        graph.add_edge("observe", "think")

    # 9. 输出治理后结束
    if has_governance:
        graph.add_edge("output_governance", END)

    graph.add_edge(START, "think")

    # 10. 设置中断点 - 权限检查前中断
    interrupt_nodes = []
    if permission_engine and has_tools:
        interrupt_nodes.append("permission_check")

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes if interrupt_nodes else None,
    )


def create_think_node(llm: Any, system_prompt: Optional[str] = None, on_token: Optional[Any] = None,
                      chain: Optional[Any] = None, prompt_assembler: Optional[Any] = None):
    """创建 Think 节点

    Args:
        on_token: 流式 token 回调 async (chunk) -> None，用于逐 token 实时输出
        chain: MiddlewareChain (LangChain AgentMiddleware 驱动链)
        prompt_assembler: PromptAssembler（Harness 层上下文组装器，设计文档 11.4）

    职责边界（设计文档 11.4）：
    - Harness：通过 PromptAssembler 组装上下文、注入系统提示词、Token 控制
    - LangGraph 节点：读取 State.messages，调用 LLM，不拼接 Prompt
    """
    from langchain_core.messages import SystemMessage

    async def think_node(state: TAOState) -> Dict[str, Any]:
        """
        Think 节点 - LLM 推理生成行动计划

        节点职责（设计文档 11.1）：
        1. 读取 State.messages（已由 Harness 组装好）
        2. 调用 LLM
        3. 提取推理和工具调用
        4. 返回 State 更新

        不做：
        - 不拼接 Prompt（由 Harness PromptAssembler 负责）
        - 不修改配置类字段
        - 不写权限判断、工具校验、日志打印
        """
        # 中间件：模型调用前（替代旧 BEFORE_THINK hook）
        if chain is not None:
            state = await chain.before_model(state)

        messages = state.get("messages", [])
        iteration = state.get("iteration", 0)

        # Harness 层上下文组装（设计文档 11.4）
        # 如果传入了 prompt_assembler，由它负责组装上下文和 Token 控制
        if prompt_assembler is not None:
            messages = prompt_assembler.assemble_with_budget(messages, system_prompt)
        else:
            # 降级：简单注入系统提示词（兼容旧代码）
            if messages and not isinstance(messages[0], SystemMessage):
                if system_prompt:
                    messages = [SystemMessage(content=system_prompt)] + messages
            elif not messages and system_prompt:
                messages = [SystemMessage(content=system_prompt)]

        # 调用 LLM - 流式生成，逐 token 透传给前端（打字机效果）
        # 每个 chunk 通过 on_token 回调实时送出，同时聚合为完整消息
        chunks = []
        async for chunk in llm.astream(messages):
            if on_token is not None:
                await on_token(chunk)
            chunks.append(chunk)

        if chunks:
            response = chunks[0]
            for c in chunks[1:]:
                response = response + c
        else:
            from langchain_core.messages import AIMessage
            response = AIMessage(content="")

        # 提取推理和工具调用（Agent 职责：思考 + 输出工具调用意图）
        # 注意：todos/State 的更新由 Runtime（observe 节点）负责，Agent 节点不做
        reasoning = extract_reasoning(response)
        tool_calls = extract_tool_calls(response)

        # 中间件：模型调用后（替代旧 AFTER_THINK hook）
        if chain is not None:
            state = await chain.after_model(state)

        return {
            "messages": [response],
            "reasoning": reasoning,
            "tool_calls": tool_calls,
            "iteration": iteration + 1,
        }

    return think_node


def create_act_node(tools: List[Any], permission_engine: Optional[Any] = None,
                    execution_manager: Optional[Any] = None):
    """创建 Act 节点 - 工具执行

    注意：权限检查在 create_permission_check_node 中完成，
    这里的 permission_engine 仅用于日志记录。
    execution_manager：Harness 工具执行门面（Phase 0 透传不拦截，Phase 1 接管执行）。
    """
    from packages.agent.tools.registry import get_tool_registry

    tool_registry = get_tool_registry()

    async def act_node(state: TAOState) -> Dict[str, Any]:
        """
        Act 节点 - 工具执行（含格式容错）

        对格式错误的工具调用（缺 name / args 非字典 / 工具不存在）做容错：
        跳过并反馈错误，供 LLM 下一轮修正，而不是中断整轮执行。
        """
        tool_calls = state.get("tool_calls", [])
        results = []
        feedback_msgs = []

        for tc in tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else None
            tool_input = tc.get("args", {}) if isinstance(tc, dict) else None

            # 格式容错 1：缺 name 或非映射结构
            if not isinstance(tc, dict) or not tool_name:
                reason = f"[工具调用格式错误] 缺少 name: {str(tc)[:120]}"
                feedback_msgs.append(reason)
                results.append({"tool": "?unknown?", "result": reason})
                continue

            # 格式容错 2：args 非字典
            if not isinstance(tool_input, dict):
                reason = f"[工具调用格式错误] {tool_name} 的 args 应为 JSON 对象: {str(tool_input)[:120]}"
                feedback_msgs.append(reason)
                results.append({"tool": tool_name, "result": reason})
                continue

            # 执行工具：必须经 Harness 工具治理门面（设计文档 2.2）——权限→清洗→按风险分流→审计
            # fail-closed：未装配治理门时拒绝执行，防止绕过治理。
            tool = tool_registry.get(tool_name)
            if tool:
                if execution_manager is not None:
                    result = await execution_manager.execute_tool(tool, tool_input)
                else:
                    reason = f"[工具执行未配置治理门，已拒绝] {tool_name}"
                    feedback_msgs.append(reason)
                    result = reason
            else:
                reason = f"[工具不存在] {tool_name}"
                feedback_msgs.append(reason)
                result = reason

            results.append({"tool": tool_name, "result": result})

        # 把格式错误反馈给 LLM（作为 system/ai 消息追加，下一轮 think 会看到）
        update: Dict[str, Any] = {
            "tool_results": results,
            "iteration": state.get("iteration", 0) + 1,
        }
        if feedback_msgs:
            from langchain_core.messages import AIMessage
            update["messages"] = [
                AIMessage(content="\n".join(feedback_msgs), name="tool_error_feedbacks")
            ]

        update = dict(update, **state)
        return update

    return act_node


def create_permission_check_node(permission_engine: Any):
    """权限检查节点 - 插入在 act 节点之前。

    治理判定收口在 `PermissionEngine.evaluate_tool_call`（Harness 层）；
    本节点只消费决策结果（allow/approve/deny）并基于 approve 构造 HITL 中断。
    """

    async def permission_check(state: TAOState) -> dict:
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return state

        pending_approvals = []
        denied = []

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_input = tc.get("args", {})

            decision = await permission_engine.evaluate_tool_call(tool_name, tool_input)

            if decision["action"] == "approve":
                pending_approvals.append(decision["pending"])
            elif decision["action"] == "deny":
                denied.append({
                    "tool": tool_name,
                    "reason": decision["reason"],
                })
            # action == "allow": 放行，交给 act 节点执行

        # 如果有需要审批的，触发中断
        if pending_approvals:
            return {
                **state,
                "__interrupt__": {
                    "type": "approval_required",
                    "pending": pending_approvals,
                },
                "tool_calls": [
                    tc for tc in tool_calls
                    if tc["name"] not in [d["tool"] for d in denied]
                ],
            }

        # 过滤掉被拒绝的
        if denied:
            deny_msgs = [
                HumanMessage(content=f"[权限拒绝] {d['tool']}: {d['reason']}")
                for d in denied
            ]
            return {
                **state,
                "tool_calls": [
                    tc for tc in tool_calls
                    if tc["name"] not in [d["tool"] for d in denied]
                ],
                "messages": state.get("messages", []) + deny_msgs,
            }

        return state

    return permission_check


def create_observe_node():
    """创建 Observe 节点 - Runtime 侧的状态整理节点。

    Runtime 职责：处理执行结果，并把 Agent 输出中的任务清单解析进 State.todos。
    注意：Agent（think 节点）不做 State 更新，只负责思考/输出工具调用/决定任务拆分。
    """

    async def observe_node(state: TAOState) -> Dict[str, Any]:
        """
        Observe 节点 - 处理工具执行结果 + 整理 State.todos

        把 act 节点产生的 tool_results 转成 ToolMessage 追加进 messages，
        使下一轮 think 能看到执行结果并据此给出最终答案（否则模型会因看不到结果而反复重调工具）。
        """
        from langchain_core.messages import ToolMessage

        messages = list(state.get("messages") or [])
        tool_results = state.get("tool_results") or []
        for r in tool_results:
            messages.append(ToolMessage(
                content=str(r.get("result", "") or ""),
                tool_call_id=str(r.get("tool_call_id", "") or ""),
                name=str(r.get("tool", "") or "") or None,
            ))

        # Runtime 职责：解析 Agent 输出中的任务清单 -> State.todos
        todos_update = _collect_todos(messages, state)

        logger.info(f"Observe: merged {len(tool_results)} tool results into messages")

        return {
            **todos_update,
            "messages": messages,
        }

    return observe_node


def _collect_todos(messages: list, state: dict) -> Dict[str, Any]:
    """从消息中的 Agent（AI）输出解析任务清单，合并进 state.todos。

    Runtime 职责：Agent 只负责"决定任务怎么拆"（在输出中表达），
    由 Runtime 解析并维护 State。
    """
    from packages.agent.runtime_engine.state import update_todos_from_message

    todos = list(state.get("todos") or [])
    for msg in messages:
        if getattr(msg, "type", "") in ("ai", "assistant"):
            content = getattr(msg, "content", "")
            if content:
                update = update_todos_from_message({"todos": todos}, content)
                todos = update.get("todos", todos)
    return {"todos": todos} if todos else {}


def create_should_act_router(max_iterations: int = 10):
    """创建路由函数"""

    def should_act(state: TAOState) -> Literal["act", "end"]:
        """
        决定是否需要行动

        终止条件:
        1. 最大轮数限制
        2. 无工具调用且有最终答案
        3. 用户取消 (外部标志)
        """
        iteration = state.get("iteration", 0)
        tool_calls = state.get("tool_calls", [])

        # 1. 最大轮数限制
        if iteration >= max_iterations:
            logger.info(f"TAO: max iterations ({max_iterations}) reached")
            return "end"

        # 2. 无工具调用，结束
        if not tool_calls:
            logger.info("TAO: no tool calls, ending")
            return "end"

        # 3. 有工具调用，继续
        return "act"

    return should_act


# ============================================================
# 辅助函数
# ============================================================

def extract_reasoning(response: AIMessage) -> str:
    """从 LLM 响应中提取推理"""
    content = response.content
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return "\n".join(str(c) for c in content)
    return ""


def extract_tool_calls(response: AIMessage) -> list:
    """从 LLM 响应中提取工具调用"""
    tool_calls = getattr(response, 'tool_calls', [])
    return tool_calls if tool_calls else []



# ============================================================
# 便捷函数
# ============================================================

async def create_tao_agent(
    llm: Any,
    tools: List[Any],
    max_iterations: int = 10,
    permission_engine: Optional[Any] = None,
) -> Any:
    """
    创建 TAO Agent

    便捷函数，封装 build_tao_graph
    """
    return build_tao_graph(llm, tools, max_iterations, permission_engine)
