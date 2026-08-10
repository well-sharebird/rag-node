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

from packages.agent.runtime.state import TAOState

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

    Returns:
        CompiledStateGraph: 编译后的图
    """
    graph = StateGraph(TAOState)

    # 1. Think 节点 - LLM 推理 (注入系统提示词)
    graph.add_node("think", create_think_node(llm, system_prompt, on_token))

    # 2. 权限检查节点 (可选)
    if permission_engine:
        graph.add_node("permission_check", create_permission_check_node(permission_engine))

    # 3. Act 节点 - 使用 LangGraph ToolNode
    if tools:
        graph.add_node("act", create_act_node(tools, permission_engine))

    # 4. Observe 节点 - 处理结果
    graph.add_node("observe", create_observe_node())

    # 5. 输出治理节点 (可选)
    if enable_output_governance and output_governance_node:
        graph.add_node("output_governance", output_governance_node)

    # 6. 条件边 - Think 后决定是 Act 还是结束
    if permission_engine:
        graph.add_conditional_edges(
            "think",
            create_should_act_router(max_iterations),
            {
                "act": "permission_check",  # 先到权限检查
                "end": "output_governance" if enable_output_governance and output_governance_node else END,
            }
        )
        graph.add_edge("permission_check", "act")
    else:
        graph.add_conditional_edges(
            "think",
            create_should_act_router(max_iterations),
            {
                "act": "act" if tools else END,
                "end": "output_governance" if enable_output_governance and output_governance_node else END,
            }
        )

    # 7. Act 后到 Observe
    if tools:
        graph.add_edge("act", "observe")
        # 8. Observe 后回到 Think (形成循环)
        graph.add_edge("observe", "think")

    # 9. 输出治理后结束
    if enable_output_governance and output_governance_node:
        graph.add_edge("output_governance", END)

    graph.add_edge(START, "think")

    # 10. 设置中断点 - 权限检查前中断
    interrupt_nodes = []
    if permission_engine:
        interrupt_nodes.append("permission_check")

    return graph.compile(interrupt_before=interrupt_nodes if interrupt_nodes else None)


def create_think_node(llm: Any, system_prompt: Optional[str] = None, on_token: Optional[Any] = None):
    """创建 Think 节点

    Args:
        on_token: 流式 token 回调 async (chunk) -> None，用于逐 token 实时输出
    """
    from packages.agent.hooks.registry import get_hook_registry, HookPoint
    from langchain_core.messages import SystemMessage

    registry = get_hook_registry()

    async def think_node(state: TAOState) -> Dict[str, Any]:
        """
        Think 节点 - LLM 推理生成行动计划
        """
        # BEFORE_THINK Hook
        if registry.has_hooks(HookPoint.BEFORE_THINK):
            state = await registry.run(HookPoint.BEFORE_THINK, state)

        messages = state.get("messages", [])
        iteration = state.get("iteration", 0)

        # 注入系统提示词 (如果是第一条消息)
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

        # 提取推理和工具调用
        reasoning = extract_reasoning(response)
        tool_calls = extract_tool_calls(response)

        # AFTER_THINK Hook
        if registry.has_hooks(HookPoint.AFTER_THINK):
            state = await registry.run(HookPoint.AFTER_THINK, state)

        return {
            "messages": [response],
            "reasoning": reasoning,
            "tool_calls": tool_calls,
            "iteration": iteration + 1,
        }

    return think_node


def create_act_node(tools: List[Any], permission_engine: Optional[Any] = None):
    """创建 Act 节点 - 工具执行

    注意：权限检查在 create_permission_check_node 中完成，
    这里的 permission_engine 仅用于日志记录
    """
    from packages.agent.hooks.registry import get_hook_registry, HookPoint
    from packages.agent.tools.registry import get_tool_registry

    tool_registry = get_tool_registry()
    hook_registry = get_hook_registry()

    async def act_node(state: TAOState) -> Dict[str, Any]:
        """
        Act 节点 - 工具执行
        """
        # BEFORE_ACT Hook
        if hook_registry.has_hooks(HookPoint.BEFORE_ACT):
            state = await hook_registry.run(HookPoint.BEFORE_ACT, state)

        tool_calls = state.get("tool_calls", [])
        results = []

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_input = tc.get("args", {})

            # 执行工具
            tool = tool_registry.get(tool_name)
            if tool:
                result = tool_registry.safe_invoke(tool, tool_input)
            else:
                result = f"[工具不存在] {tool_name}"

            results.append({"tool": tool_name, "result": result})

        # AFTER_ACT Hook
        if hook_registry.has_hooks(HookPoint.AFTER_ACT):
            state = await hook_registry.run(HookPoint.AFTER_ACT, state)

        return {
            **state,
            "tool_results": results,
            "iteration": state.get("iteration", 0) + 1,
        }

    return act_node


def create_permission_check_node(permission_engine: Any):
    """权限检查节点 - 插入在 act 节点之前"""

    async def permission_check(state: TAOState) -> dict:
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return state

        pending_approvals = []
        denied = []

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_input = tc.get("args", {})

            # 调用 PermissionEngine 检查权限
            has_permission, request = await permission_engine.check_permission(
                tool_name=tool_name,
                operation="execute",
                parameters=tool_input,
            )

            if not has_permission and request:
                from packages.agent.runtime_engine.permission import PermissionLevel

                if request.permission_level == PermissionLevel.APPROVE_ONCE:
                    # 需要审批
                    pending_approvals.append({
                        "tool": tool_name,
                        "args": tool_input,
                        "risk_level": request.risk_level,
                        "request_id": request.id,
                    })
                elif request.permission_level == PermissionLevel.ASK_FIRST:
                    # 首次询问，等待用户确认
                    pending_approvals.append({
                        "tool": tool_name,
                        "args": tool_input,
                        "risk_level": request.risk_level,
                        "request_id": request.id,
                    })
                else:
                    # 拒绝
                    denied.append({
                        "tool": tool_name,
                        "reason": f"权限不足：{request.reason}",
                    })

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
    """创建 Observe 节点"""

    async def observe_node(state: TAOState) -> Dict[str, Any]:
        """
        Observe 节点 - 处理工具执行结果
        """
        # 从消息中提取工具执行结果
        messages = state.get("messages", [])
        tool_results = extract_tool_results(messages)

        logger.info(
            f"Observe: processed {len(tool_results)} tool results"
        )

        return {
            "messages": [],  # 结果已在消息中
        }

    return observe_node


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


def extract_tool_results(messages: List[BaseMessage]) -> list:
    """从消息中提取工具执行结果"""
    results = []
    for msg in messages:
        if hasattr(msg, 'type') and msg.type == 'tool':
            results.append({
                'tool_call_id': getattr(msg, 'tool_call_id', None),
                'content': msg.content,
            })
    return results


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
