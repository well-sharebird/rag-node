"""
运行时引擎（参考 DeerFlow 设计）

核心职责：
1. 状态机管理：初始化 → 执行 → 暂停 → 恢复 → 完成
2. 消息编排：构造 LLM 消息，处理响应
3. 异步执行：事件流广播
4. 超时和中断：超时控制，任务中断
5. 中间件链管理
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, AsyncGenerator

from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.graph.state import CompiledStateGraph

from .middleware import RuntimeContext, MiddlewareChain
from .state import AgentState

from packages.agent.schemas.stream import ev_state_update

logger = logging.getLogger(__name__)


class RuntimeEngine:
    """
    运行时引擎（统一管理 Agent 执行）
    
    核心设计：
    - 使用中间件链管理横切关注点
    - LangGraph 控制循环
    - 统一的运行时上下文
    - 纯 Agent Loop 图（think→act→think）
    """
    
    def __init__(
        self,
        llm: Any,
        tools: Optional[List[Any]] = None,
        middlewares: Optional[List[Any]] = None,
        hook_registry: Optional[Any] = None,
        max_iterations: int = 10,
        permission_engine: Optional[Any] = None,
        system_prompt: Optional[str] = None,
        checkpointer: Optional[Any] = None,
    ):
        """
        初始化运行时引擎
        
        Args:
            llm: LLM 实例
            tools: 工具列表（可选）
            middlewares: 中间件列表
            hook_registry: HookRegistry 实例（向后兼容）
            max_iterations: 最大迭代次数
            permission_engine: 权限引擎（可选）
            system_prompt: 系统提示词（可选）
            checkpointer: LangGraph checkpointer（可选）
        """
        # 保存参数（先保存，避免_build_graph 访问时不存在）
        self._llm = llm
        self._tools = tools or []
        self._hook_registry = hook_registry
        self._max_iterations = max_iterations
        self._permission_engine = permission_engine
        self._system_prompt = system_prompt
        self._checkpointer = checkpointer
        self._middleware_chain = None  # Will be initialized after building graph
        
        # 构建中间件链
        middleware_list = list(middlewares) if middlewares else []
        
        # 添加 Hooks 适配器（向后兼容）
        if hook_registry is not None:
            from .adapters import HooksAdapterMiddleware
            middleware_list.insert(0, HooksAdapterMiddleware(hook_registry))
            logger.info("[RuntimeEngine] HooksAdapterMiddleware added for backward compatibility")
        
        # 构建纯 Agent Loop 图
        self._graph = self._build_graph(
            llm=llm,
            tools=tools or [],
            middleware_list=middleware_list,
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )
        
        # 初始化中间件链（在_build_graph 之后）
        self._middleware_chain = MiddlewareChain(middleware_list)
        self._last_message = None  # Track last AI message for done event
    
    def _build_graph(
        self,
        llm: Any,
        tools: List[Any],
        middleware_list: List[Any],
        max_iterations: int,
        permission_engine: Optional[Any],
        system_prompt: Optional[str],
        checkpointer: Optional[Any],
    ) -> CompiledStateGraph:
        """
        构建纯 Agent Loop 图
        
        Args:
            llm: LLM 实例
            tools: 工具列表
            middleware_list: 中间件列表
            max_iterations: 最大迭代次数
            permission_engine: 权限引擎
            system_prompt: 系统提示词
            checkpointer: LangGraph checkpointer
        
        Returns:
            CompiledStateGraph: 编译后的图
        """
        from .graph import build_agent_graph
        
        return build_agent_graph(
            llm=llm,
            tools=tools,
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            middlewares=middleware_list,
            hooks=self._hook_registry,
        )
    
    async def execute(
        self,
        query: str,
        thread_id: str,
        user_id: int,
        session_id: Optional[str] = None,
        history: Optional[List[BaseMessage]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行一次任务
        
        Args:
            query: 用户查询
            thread_id: 线程 ID
            user_id: 用户 ID
            session_id: 会话 ID（可选）
            history: 历史消息（可选）
            **kwargs: 扩展参数
            
        Yields:
            执行事件（SSE 格式）
        """
        # 1. 创建运行时上下文
        runtime = RuntimeContext(
            thread_id=thread_id,
            user_id=user_id,
            session_id=session_id,
            **kwargs,
        )
        
        # 2. 初始化状态
        messages = (history or []) + [HumanMessage(content=query)]
        state: AgentState = {
            "messages": messages,
            "iteration": 0,
            "tool_calls": [],
            "tool_results": [],
        }
        
        # 3. 执行中间件 before_agent
        logger.info("[RuntimeEngine] Executing %d middlewares (before_agent)", len(self._middleware_chain.middlewares))
        state = await self._middleware_chain.before_agent(state, runtime)
        
        # 4. 检查是否被中间件中断
        if state.get("_force_end"):
            logger.warning("[RuntimeEngine] Forced end by middleware: %s", state.get("_end_reason"))
            yield {"type": "forced_end", "reason": state.get("_end_reason")}
            return
        
        # 5. 运行 Agent（使用 LangGraph astream + stream_mode="messages" 实现真正流式）
        try:
            # 构建图（使用已有的 build_agent_graph）
            from .graph import build_agent_graph
            
            # 创建流式事件队列（用于从 think_node 实时接收事件）
            import asyncio
            event_queue = asyncio.Queue()
            
            # 创建流式事件回调（think_node 会调用这个回调发送细粒度事件）
            import time
            event_count = 0
            
            async def on_stream_event(event: dict):
                """流式事件回调 - 将事件放入队列"""
                nonlocal event_count
                event_count += 1
                recv_time = time.time()
                event_type = event.get('type', 'unknown')
                await event_queue.put(event)
                put_time = time.time()
                if event_count <= 5 or event_count % 50 == 0:
                    logger.warning(f"[RuntimeEngine.on_stream_event] 📨 {event_type} #{event_count} @ {recv_time:.3f} (queue_put={(put_time-recv_time)*1000:.1f}ms)")
            
            graph = build_agent_graph(
                llm=self._llm,
                tools=self._tools,
                max_iterations=self._max_iterations,
                permission_engine=self._permission_engine,
                system_prompt=self._system_prompt,
                on_stream_event=on_stream_event,  # 传递流式事件回调
                checkpointer=self._checkpointer,
                middlewares=self._middleware_chain.middlewares,
                hooks=self._hook_registry,
            )
            
            # 准备配置
            config = {
                "configurable": {
                    "thread_id": runtime.thread_id,
                    "user_id": runtime.user_id,
                },
                "recursion_limit": self._max_iterations * 2,
            }
            
            # 使用 stream_mode="messages" 获取流式消息（LangGraph 原生支持）
            logger.info("[RuntimeEngine] Starting graph astream with stream_mode='messages'")
            
            seen_ids: set[str] = set()
            
            # 启动 graph.astream() 后台任务（这会触发 think_node 中的 on_stream_event 回调）
            import time
            stream_start = time.time()
            drain_count = 0
            logger.warning(f"[RuntimeEngine] 🚀 Starting graph astream + queue drain")
            
            # 创建后台任务执行 graph
            async def run_graph():
                """后台执行 graph，事件通过 on_stream_event 回调发送"""
                try:
                    async for chunk in graph.astream(state, config=config, stream_mode="messages"):
                        pass  # chunk 不需要，事件已通过回调发送
                    logger.warning(f"[RuntimeEngine] ✅ Graph astream complete")
                except Exception as e:
                    logger.exception("[RuntimeEngine] Graph stream failed: %s", e)
                    raise
            
            graph_task = asyncio.create_task(run_graph())
            
            try:
                # Drain 事件队列（实时发送）
                while True:
                    try:
                        # 等待并获取事件
                        fine_grained_event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                        drain_count += 1
                        drain_time = time.time()
                        event_type = fine_grained_event.get('type', 'unknown')
                        
                        if drain_count <= 5 or drain_count % 50 == 0:
                            logger.warning(f"[RuntimeEngine] 📤 drain {event_type} #{drain_count} @ {drain_time:.3f} (elapsed={(drain_time-stream_start)*1000:.0f}ms)")
                        
                        yield fine_grained_event
                    except asyncio.TimeoutError:
                        # 检查 graph 是否完成
                        if graph_task.done():
                            # 最后一次尝试 drain 剩余事件
                            while not event_queue.empty():
                                try:
                                    fine_grained_event = event_queue.get_nowait()
                                    drain_count += 1
                                    yield fine_grained_event
                                except asyncio.QueueEmpty:
                                    break
                            break
                        # graph 还在运行，继续等待
                
                # 等待 graph 完成
                await graph_task
                
            except Exception as e:
                # 取消 graph 任务
                graph_task.cancel()
                raise
            
            logger.warning(f"[RuntimeEngine] ✅ Queue drain complete: {drain_count} events in {(time.time()-stream_start)*1000:.0f}ms")
            
            # 发送完成事件
            from packages.agent.schemas.stream import ev_done
            yield ev_done(reason="completed")
            
            logger.info("[RuntimeEngine] Graph astream complete")
            
        except Exception as e:
            logger.exception("[RuntimeEngine] Agent stream failed: %s", e)
            yield {"type": "error", "message": str(e)}
            raise
    
    async def _run_graph(
        self,
        state: AgentState,
        runtime: RuntimeContext,
        event_queue: Optional[asyncio.Queue] = None,
        on_stream_event: Optional[Any] = None,  # 流式事件回调
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行 LangGraph（控制循环）
        
        Args:
            state: 初始状态
            runtime: 运行时上下文
            event_queue: 事件队列
            on_stream_event: 流式事件回调
            
        Yields:
            图执行事件
        """
        # 构建图配置
        config = {
            "configurable": {
                "thread_id": runtime.thread_id,
            },
            "recursion_limit": self._max_iterations * 2,  # 每轮迭代最多 2 次递归（think + act）
        }
        
        # 运行图
        logger.info("[RuntimeEngine] Starting graph execution")
        
        try:
            # 重新构建图（带 event_queue 和 on_stream_event）
            from .graph import build_agent_graph
            graph = build_agent_graph(
                llm=self._llm,
                tools=self._tools,
                max_iterations=self._max_iterations,
                permission_engine=self._permission_engine,
                system_prompt=self._system_prompt,
                on_stream_event=on_stream_event,  # 传递流式事件回调
                checkpointer=self._checkpointer,
                middlewares=self._middleware_chain.middlewares,
                hooks=self._hook_registry,
            )
            
            # 使用 astream 运行图
            async for event in graph.astream(state, config=config):
                # 转发图事件
                yield self._format_event(event, runtime)
                
                # 检查中断
                if self._should_interrupt(event):
                    logger.info("[RuntimeEngine] Interrupting graph execution")
                    break
            
            # Drain 事件队列（细粒度事件）
            if event_queue is not None:
                while not event_queue.empty():
                    try:
                        fine_grained_event = event_queue.get_nowait()
                        yield fine_grained_event
                    except asyncio.QueueEmpty:
                        break
                    
        except Exception as e:
            logger.exception("[RuntimeEngine] Graph execution failed: %s", e)
            raise
    
    def _format_event(self, event: Dict[str, Any], runtime: RuntimeContext) -> Dict[str, Any]:
        """
        格式化图事件为 SSE 格式（支持 Qwen3.5 reasoning 字段）
        
        LangGraph 事件结构：
        - stream_mode="updates": {'think': {'messages': [...], 'reasoning': '...', ...}}
        - stream_mode="values": {'messages': [...], 'reasoning': '...', ...}
        
        Args:
            event: 图事件
            runtime: 运行时上下文
            
        Returns:
            SSE 格式事件
        """
        # 处理 LangGraph 嵌套结构（节点名作为 key）
        # 例如：{'think': {'messages': [...], 'reasoning': '...', ...}}
        node_data = None
        for key in ['think', 'act', 'observe', 'permission_check', 'output_governance']:
            if key in event:
                node_data = event[key]
                break
        
        # 如果没有找到节点数据，直接使用 event
        if node_data is None:
            node_data = event
        
        # 提取关键信息
        messages = node_data.get("messages", [])
        tool_calls = node_data.get("tool_calls", [])
        reasoning = node_data.get("reasoning", "")
        iteration = node_data.get("iteration", 0)
        
        # 包含 reasoning 字段（Qwen3.5 模型）
        data = {
            "iteration": iteration,
            "messages_count": len(messages),
            "tool_calls_count": len(tool_calls),
        }
        
        if reasoning:
            data["reasoning"] = reasoning
        
        # 如果有新消息，单独发送
        if messages:
            last_msg = messages[-1]
            # 跟踪最后一条 AI 消息（检查类型而非 role 属性）
            from langchain_core.messages import AIMessage, AIMessageChunk
            if isinstance(last_msg, (AIMessage, AIMessageChunk)):
                self._last_message = last_msg
            content = getattr(last_msg, "content", "")
            # 如果 content 为空但有 reasoning，使用 reasoning
            if not content and reasoning:
                content = reasoning
            data["last_message"] = {
                "role": getattr(last_msg, "role", "unknown"),
                "content": content[:200],  # 截断预览
            }
        
        # 使用工厂函数
        return ev_state_update(**data)
    
    def _should_interrupt(self, event: Dict[str, Any]) -> bool:
        """
        检查是否应该中断图执行
        
        Args:
            event: 图事件
            
        Returns:
            True 表示应该中断
        """
        # 检查强制结束标记
        if event.get("_force_end"):
            return True
        
        # 检查澄清请求
        if event.get("_interrupt") == "clarification":
            return True
        
        # 检查迭代次数
        iteration = event.get("iteration", 0)
        if iteration >= self._max_iterations:
            return True
        
        return False


def make_agent(
    llm: Any,
    tools: Optional[List[Any]] = None,
    middlewares: Optional[List[Any]] = None,
    hook_registry: Optional[Any] = None,
    max_iterations: int = 10,
    permission_engine: Optional[Any] = None,
    system_prompt: Optional[str] = None,
    checkpointer: Optional[Any] = None,
) -> RuntimeEngine:
    """
    工厂方法：创建 Agent 运行时引擎
    
    Args:
        llm: LLM 实例
        tools: 工具列表（可选）
        middlewares: 中间件列表（默认使用内置中间件）
        hook_registry: HookRegistry 实例（向后兼容）
        max_iterations: 最大迭代次数
        permission_engine: 权限引擎（可选）
        system_prompt: 系统提示词（可选）
        checkpointer: LangGraph checkpointer（可选）
        
    Returns:
        RuntimeEngine 实例
    """
    from .builtins import build_default_middlewares
    
    # 使用默认中间件（如果没有提供）
    if middlewares is None:
        middlewares = build_default_middlewares()
    
    # 创建引擎
    engine = RuntimeEngine(
        llm=llm,
        tools=tools,
        middlewares=middlewares,
        hook_registry=hook_registry,
        max_iterations=max_iterations,
        permission_engine=permission_engine,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )
    
    logger.info("[make_agent] Created RuntimeEngine with %d middlewares, hook_registry=%s", 
                len(middlewares), "yes" if hook_registry else "no")
    
    return engine
