"""
Agent Graph - 纯 Agent Loop 实现

核心设计：
1. 纯 Agent Loop：think → act → think 循环
2. 无 Orchestrator 节点：Orchestrator 在图外控制
3. 中间件链管理横切关注点
4. 支持工具执行、权限检查、输出治理

架构：
```
RuntimeEngine (运行时引擎)
    ↓
MiddlewareChain (中间件链)
    ↓
Agent Graph (纯 Agent Loop)
    ├── think 节点 (模型调用)
    ├── permission_check 节点 (可选)
    ├── act 节点 (工具执行)
    └── observe 节点 (结果处理)
    ↓
Orchestrator (图外编排器)
```
"""
import logging
from typing import Any, Dict, List, Literal, Optional
import asyncio

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from packages.agent.runtime.middleware import MiddlewareChain

from packages.agent.runtime.state import AgentState

logger = logging.getLogger(__name__)


def build_agent_graph(
    llm: Any,
    tools: List[Any],
    max_iterations: int = 10,
    permission_engine: Optional[Any] = None,
    enable_output_governance: bool = True,
    output_governance_node: Optional[Any] = None,
    system_prompt: Optional[str] = None,
    on_token: Optional[Any] = None,
    on_stream_event: Optional[Any] = None,  # 流式事件回调（用于细粒度事件）
    checkpointer: Optional[Any] = None,
    middlewares: Optional[List[Any]] = None,
    hooks: Optional[Any] = None,
) -> CompiledStateGraph:
    """
    构建纯 Agent Loop 图
    
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
        middlewares: 中间件列表
        hooks: HookRegistry（可选，支持 waterfall 拦截器，向后兼容）
    
    Returns:
        CompiledStateGraph: 编译后的图
    """
    # 构建中间件链
    chain = MiddlewareChain(middlewares or [])
    
    graph = StateGraph(AgentState)
    
    # 1. Think 节点 - LLM 推理（支持中间件和 hooks）
    graph.add_node(
        "think",
        create_think_node(
            llm=llm,
            system_prompt=system_prompt,
            on_token=on_token,
            middleware_chain=chain,
            hooks=hooks,
            on_stream_event=on_stream_event,
        )
    )
    
    # 2. 权限检查节点 (可选)
    has_tools = bool(tools)
    if permission_engine and has_tools:
        graph.add_node(
            "permission_check",
            create_permission_check_node(permission_engine)
        )
    
    # 3. Act 节点 - 工具执行（支持 hooks waterfall）
    if has_tools:
        graph.add_node(
            "act",
            create_act_node(
                tools=tools,
                permission_engine=permission_engine,
                hooks=hooks,
            )
        )
    
    # 4. Observe 节点 - 处理结果
    graph.add_node("observe", create_observe_node())
    
    # 5. 输出治理节点 (可选)
    has_governance = enable_output_governance and output_governance_node
    if has_governance:
        graph.add_node("output_governance", output_governance_node)
    
    # 6. Think 后决定是 Act 还是结束
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
        # 8. Observe 后回到 Think（形成循环）
        graph.add_edge("observe", "think")
    
    # 9. 输出治理后结束
    if has_governance:
        graph.add_edge("output_governance", END)
    
    # 10. START 到 Think（入口）
    graph.add_edge(START, "think")
    
    # 11. 设置中断点 - 权限检查前中断
    interrupt_nodes = []
    if permission_engine and has_tools:
        interrupt_nodes.append("permission_check")
    
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes if interrupt_nodes else None,
    )


def create_think_node(
    llm: Any,
    system_prompt: Optional[str] = None,
    on_token: Optional[Any] = None,
    middleware_chain: Optional[MiddlewareChain] = None,
    hooks: Optional[Any] = None,
    on_stream_event: Optional[Any] = None,  # 流式事件回调 async (event: dict) -> None
):
    """
    创建 Think 节点 - LLM 推理
    
    Args:
        llm: LLM 实例
        system_prompt: 系统提示词
        on_token: 流式 token 回调
        middleware_chain: 中间件链
        hooks: HookRegistry（向后兼容）
        on_stream_event: 流式事件回调（用于发送细粒度事件到 API 层）
    
    职责：
    1. 读取 AgentState.messages
    2. 执行 before_agent 中间件
    3. 调用 LLM
    4. 执行 after_agent 中间件
    5. 提取推理和工具调用
    """
    from langchain_core.messages import SystemMessage
    
    from langgraph._internal._runnable import RunnableConfig
    
    async def think_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
        """Think 节点 - LLM 推理"""
        # 从 config 提取 runtime 上下文
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        user_id = config.get("configurable", {}).get("user_id", 0)
        
        from packages.agent.runtime.middleware import RuntimeContext
        runtime = RuntimeContext(thread_id=thread_id, user_id=user_id)
        
        # 中间件：模型调用前
        if middleware_chain:
            state = await middleware_chain.before_agent(state, runtime)
        
        messages = state.get("messages", [])
        iteration = state.get("iteration", 0)
        
        # Hooks waterfall: 在 LLM 调用前拦截 messages（向后兼容）
        if hooks and hasattr(hooks, 'run_waterfall'):
            messages = await hooks.run_waterfall('llm/messages', messages)
        
        # 注入系统提示词
        if messages and not isinstance(messages[0], SystemMessage):
            if system_prompt:
                messages = [SystemMessage(content=system_prompt)] + messages
        elif not messages and system_prompt:
            messages = [SystemMessage(content=system_prompt)]
        
        # 调用 LLM - 流式生成（Qwen3.5 同时返回 reasoning 和 content）
        # Qwen3.5 返回模式：
        # 1. 先输出 reasoning（思考过程，约 380 chunks）
        # 2. 后输出 content（最终答案，约 10 chunks）
        # 需要分别累加
        chunks = []
        reasoning_parts = []
        content_parts = []
        
        # 流式处理：通过 callback 实时发送细粒度事件
        import time
        chunk_count = 0
        logger.warning("[think_node] 🚀 Starting LLM stream")
        
        async for chunk in llm.astream(messages):
            chunk_time = time.time()
            chunk_count += 1
            
            if on_token is not None:
                await on_token(chunk)
            chunks.append(chunk)
            
            # 提取 chunk 内容（AIMessageChunk 没有 delta 属性）
            # reasoning 在 additional_kwargs 中
            additional_kwargs = getattr(chunk, 'additional_kwargs', {}) or {}
            content = getattr(chunk, 'content', '')
            
            # 调试日志：查看每个 chunk 的结构
            if chunk_count <= 5 or chunk_count % 50 == 0:
                logger.warning(f"[think_node] chunk #{chunk_count}: content='{content[:50] if content else ''}', reasoning='{additional_kwargs.get('reasoning', '')[:50] if additional_kwargs.get('reasoning') else ''}'")
            
            # 检查是否是 reasoning chunk
            if 'reasoning' in additional_kwargs and additional_kwargs['reasoning']:
                reasoning_parts.append(additional_kwargs['reasoning'])
                # 🚀 实时发送事件（阻塞确保顺序和时机）
                if on_stream_event is not None:
                    try:
                        from packages.agent.schemas.stream import ev_reasoning
                        event = ev_reasoning(content=additional_kwargs['reasoning'])
                        send_start = time.time()
                        await on_stream_event(event)  # ✅ 直接 await，确保实时发送
                        send_duration = (time.time() - send_start) * 1000
                        if chunk_count <= 5 or chunk_count % 50 == 0:
                            logger.warning(f"[think_node] 📤 reasoning chunk #{chunk_count} @ {chunk_time:.3f} (send={send_duration:.1f}ms)")
                    except Exception as e:
                        logger.warning(f"[think_node] Failed to emit reasoning event: {e}")
            
            # 发送 content token（reasoning 和 content 是独立的，分别发送）
            if content:
                content_parts.append(content)
                # 🚀 实时发送事件（阻塞确保顺序和时机）
                if on_stream_event is not None:
                    try:
                        from packages.agent.schemas.stream import ev_token
                        event = ev_token(content=content)
                        send_start = time.time()
                        await on_stream_event(event)  # ✅ 直接 await，确保实时发送
                        send_duration = (time.time() - send_start) * 1000
                        if chunk_count <= 5 or chunk_count % 50 == 0:
                            logger.warning(f"[think_node] 📤 token chunk #{chunk_count} @ {chunk_time:.3f} (send={send_duration:.1f}ms)")
                    except Exception as e:
                        logger.warning(f"[think_node] Failed to emit token event: {e}")
        
        logger.warning(f"[think_node] ✅ LLM stream complete: {chunk_count} chunks, {len(reasoning_parts)} reasoning, {len(content_parts)} content")
        
        # 构建完整响应
        if chunks:
            response = chunks[0]
            for c in chunks[1:]:
                response = response + c
        else:
            response = AIMessage(content="")
        
        # 保存累加的 reasoning 到 additional_kwargs
        full_reasoning = "".join(reasoning_parts) if reasoning_parts else ""
        full_content = "".join(content_parts) if content_parts else ""
        
        if not hasattr(response, 'additional_kwargs') or not response.additional_kwargs:
            response.additional_kwargs = {}
        
        # 保存 reasoning（如果有）
        if full_reasoning:
            response.additional_kwargs['reasoning'] = full_reasoning
        
        # Hooks waterfall: 在 LLM 调用后拦截 response（向后兼容）
        if hooks and hasattr(hooks, 'run_waterfall'):
            response = await hooks.run_waterfall('llm/response', response)
        
        # 提取推理和工具调用
        reasoning = extract_reasoning(response)
        tool_calls = extract_tool_calls(response)
        
        # 中间件：模型调用后
        if middleware_chain:
            state = await middleware_chain.after_agent(state, runtime, response)
        
        return {
            "messages": [response],
            "reasoning": reasoning,
            "tool_calls": tool_calls,
            "iteration": iteration + 1,
        }
    
    return think_node


def create_should_act_router(max_iterations: int = 10):
    """
    创建路由函数 - 决定 Think 后是否执行工具
    
    终止条件：
    1. 最大轮数限制
    2. 无工具调用
    """
    def should_act(state: AgentState) -> Literal["act", "end"]:
        iteration = state.get("iteration", 0)
        tool_calls = state.get("tool_calls", [])
        
        # 1. 最大轮数限制
        if iteration >= max_iterations:
            logger.info(f"Agent Graph: max iterations ({max_iterations}) reached")
            return "end"
        
        # 2. 无工具调用，结束
        if not tool_calls:
            logger.info("Agent Graph: no tool calls, ending")
            return "end"
        
        # 3. 有工具调用，继续执行
        return "act"
    
    return should_act


def create_act_node(
    tools: List[Any],
    permission_engine: Optional[Any] = None,
    hooks: Optional[Any] = None,
):
    """
    创建 Act 节点 - 工具执行
    
    Args:
        tools: 工具列表
        permission_engine: 权限引擎（用于日志记录）
        hooks: HookRegistry（向后兼容）
    
    职责：
    1. 执行工具调用
    2. 支持格式容错
    3. 支持 hooks waterfall 拦截
    """
    from packages.agent.tools.registry import get_tool_registry
    
    tool_registry = get_tool_registry()
    
    async def act_node(state: AgentState) -> Dict[str, Any]:
        """Act 节点 - 工具执行"""
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
                reason = f"[工具调用格式错误] {tool_name} 的 args 应为 JSON 对象：{str(tool_input)[:120]}"
                feedback_msgs.append(reason)
                results.append({"tool": tool_name, "result": reason})
                continue
            
            # Hooks waterfall: 在工具执行前拦截 tool_input（向后兼容）
            if hooks and hasattr(hooks, 'run_waterfall'):
                tool_input = await hooks.run_waterfall('tools/input', tool_input)
            
            # 执行工具
            tool = tool_registry.get(tool_name)
            if tool:
                # TODO: 集成工具执行管理器
                try:
                    result = await tool.ainvoke(tool_input)
                except Exception as e:
                    result = f"[工具执行异常] {str(e)}"
                    logger.error(f"Tool execution error: {result}")
            else:
                reason = f"[工具不存在] {tool_name}"
                feedback_msgs.append(reason)
                result = reason
            
            # Hooks waterfall: 在工具执行后拦截 result（向后兼容）
            if hooks and hasattr(hooks, 'run_waterfall'):
                result = await hooks.run_waterfall('tools/output', result)
            
            results.append({"tool": tool_name, "result": result})
        
        # 把格式错误反馈给 LLM
        update: Dict[str, Any] = {
            "tool_results": results,
        }
        if feedback_msgs:
            update["messages"] = [
                AIMessage(content="\n".join(feedback_msgs), name="tool_error_feedbacks")
            ]
        
        return update
    
    return act_node


def create_permission_check_node(permission_engine: Any):
    """
    权限检查节点 - 插入在 act 节点之前
    
    职责：
    1. 评估每个工具调用的权限
    2. 触发 HITL 中断（如果需要审批）
    3. 拒绝未授权的调用
    """
    async def permission_check(state: AgentState) -> dict:
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return state
        
        pending_approvals = []
        denied = []
        
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_input = tc.get("args", {})
            
            # TODO: 调用权限引擎评估
            # decision = await permission_engine.evaluate_tool_call(tool_name, tool_input)
            
            # 临时实现：直接放行
            # TODO: 实现完整的权限检查逻辑
            
        # 如果有需要审批的，触发中断
        if pending_approvals:
            thread_id = state.get("session_id") or state.get("thread_id", "unknown")
            
            for p in pending_approvals:
                if isinstance(p, dict):
                    p["thread_id"] = thread_id
            
            return {
                **state,
                "__interrupt__": {
                    "type": "approval_required",
                    "pending_approvals": pending_approvals,
                },
            }
        
        # 如果有被拒绝的，反馈给 LLM
        if denied:
            from langchain_core.messages import AIMessage
            feedback = "\n".join([f"[权限拒绝] {d['tool']}: {d['reason']}" for d in denied])
            return {
                **state,
                "messages": [AIMessage(content=feedback, name="permission_denied")],
                "tool_calls": [],  # 清空工具调用，阻止执行
            }
        
        return state
    
    return permission_check


def create_observe_node():
    """
    创建 Observe 节点 - 处理结果
    
    职责：
    1. 整理工具执行结果
    2. 更新迭代次数
    3. 准备下一轮循环
    """
    async def observe_node(state: AgentState) -> Dict[str, Any]:
        """Observe 节点 - 处理结果"""
        tool_results = state.get("tool_results", [])
        iteration = state.get("iteration", 0)
        
        # 将工具结果转换为消息格式
        if tool_results:
            result_content = "\n".join([
                f"工具：{r.get('tool', 'unknown')}\n结果：{r.get('result', 'no result')}"
                for r in tool_results
            ])
            
            from langchain_core.messages import HumanMessage
            return {
                "messages": [HumanMessage(content=result_content, name="tool_results")],
                "iteration": iteration + 1,
            }
        
        return {"iteration": iteration + 1}
    
    return observe_node


def extract_reasoning(response: AIMessage) -> str:
    """
    提取推理内容（支持 Qwen3.5 reasoning 字段）
    
    Args:
        response: LLM 响应消息
    
    Returns:
        推理文本
    """
    # 1. 优先提取思维链 (reasoning_content 字段)
    if hasattr(response, 'reasoning_content') and response.reasoning_content:
        return response.reasoning_content
    
    # 2. 尝试从 additional_kwargs 提取（流式累加的 reasoning）
    if hasattr(response, 'additional_kwargs') and response.additional_kwargs:
        reasoning = response.additional_kwargs.get('reasoning')
        if reasoning:
            return reasoning
    
    # 3. 尝试从 response_metadata 提取 Qwen3.5 的 reasoning 字段
    # Qwen3.5 返回：choices[0].message.reasoning (而非 content)
    if hasattr(response, 'response_metadata') and response.response_metadata:
        # 流式响应：response_metadata 可能包含 choices
        choices = response.response_metadata.get('choices', [])
        if choices and len(choices) > 0:
            message = choices[0].get('message', {})
            reasoning = message.get('reasoning')
            if reasoning:
                return reasoning
    
    # 4. 降级：使用 content
    return response.content or ""


def extract_tool_calls(response: AIMessage) -> List[Dict[str, Any]]:
    """
    提取工具调用
    
    Args:
        response: LLM 响应消息
    
    Returns:
        工具调用列表
    """
    tool_calls = []
    
    # 提取 LangChain 工具调用
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": tc.get("name", ""),
                "args": tc.get("args", {}),
            })
    
    # 提取额外工具调用（如果有）
    if hasattr(response, 'additional_kwargs'):
        extra = response.additional_kwargs
        if 'tool_calls' in extra:
            for tc in extra['tool_calls']:
                if isinstance(tc, dict):
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "args": tc.get("function", {}).get("arguments", {}),
                    })
    
    return tool_calls
