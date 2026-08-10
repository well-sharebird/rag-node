"""
Agent Runtime - Runtime 层核心封装

解决"怎么跑"的问题 - 提供生产环境基础设施能力：
- 持久化执行 (CheckpointSaver)
- 流式支持 (astream/stream_mode)
- 人机协作中断 (interrupt/resume)
- 线程级持久化 (thread_id 隔离)
- 状态快照 (get_state/patch_state)
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional, AsyncGenerator, Any, Dict, List
from dataclasses import dataclass
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.runnables import RunnableConfig

from packages.agent.runtime.config import RuntimeConfig

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    result: Optional[Any] = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def ok(cls, result: Any, duration_ms: int = 0, metadata: Optional[Dict] = None):
        return cls(success=True, result=result, duration_ms=duration_ms, metadata=metadata)

    @classmethod
    def error(cls, error_message: str, duration_ms: int = 0):
        return cls(success=False, error_message=error_message, duration_ms=duration_ms)


class AgentRuntime:
    """
    Agent 运行时 - Runtime 层统一执行入口

    封装 LangGraph 的执行能力，提供：
    1. 统一执行入口 (execute/stream/interrupt/resume)
    2. 资源管理 (Token 预算/超时/重试)
    3. 状态管理 (Checkpoint/恢复/时间旅行)
    """

    def __init__(
        self,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        config: Optional[RuntimeConfig] = None,
    ):
        self.checkpointer = checkpointer
        self.config = config or RuntimeConfig()
        self._active_executions: Dict[str, Dict[str, Any]] = {}

    async def execute(
        self,
        graph: CompiledStateGraph,
        state: dict,
        thread_id: str,
        run_id: Optional[str] = None,
        callbacks: Optional[list] = None,
    ) -> ExecutionResult:
        """
        批量执行 - 统一执行入口

        Args:
            graph: 编译后的 LangGraph
            state: 初始状态
            thread_id: 线程 ID (用于隔离)
            run_id: 运行 ID (用于追踪)
            callbacks: LangGraph 回调列表 (可选)

        Returns:
            ExecutionResult: 执行结果
        """
        start_time = datetime.utcnow()
        run_id = run_id or str(uuid4())

        # 构建 LangGraph 配置
        config = await self._build_config(thread_id, run_id, callbacks)

        try:
            # 执行
            result = await asyncio.wait_for(
                graph.ainvoke(state, config=config),
                timeout=self.config.timeout_seconds,
            )

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # 记录执行
            self._record_execution(run_id, "completed", result)

            return ExecutionResult.ok(result, duration_ms, {"run_id": run_id})

        except asyncio.TimeoutError:
            self._record_execution(run_id, "timeout", None)
            return ExecutionResult.error(
                f"Execution timeout after {self.config.timeout_seconds}s",
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
            )
        except Exception as e:
            self._record_execution(run_id, "failed", None)
            logger.exception(f"Execution failed | run={run_id}")
            return ExecutionResult.error(
                str(e),
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
            )

    async def execute_stream(
        self,
        graph: CompiledStateGraph,
        state: dict,
        thread_id: str,
        run_id: Optional[str] = None,
        stream_mode: str = "messages",
        callbacks: Optional[list] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行

        Args:
            graph: 编译后的 LangGraph
            state: 初始状态
            thread_id: 线程 ID
            run_id: 运行 ID
            stream_mode: 流式模式 (messages, values, updates)
            callbacks: LangGraph 回调列表 (可选)

        Yields:
            Dict: 流式事件
        """
        run_id = run_id or str(uuid4())
        config = await self._build_config(thread_id, run_id, callbacks)

        try:
            # 记录执行开始
            self._record_execution(run_id, "running", None)

            # 流式执行
            async for event, metadata in graph.astream(
                state,
                config=config,
                stream_mode=stream_mode,
            ):
                yield self._format_event(event, metadata, run_id)

            # 记录执行完成
            self._record_execution(run_id, "completed", None)

        except Exception as e:
            logger.exception(f"Stream execution failed | run={run_id}")
            yield {
                "type": "error",
                "run_id": run_id,
                "error": str(e),
            }
            self._record_execution(run_id, "failed", None)

    async def interrupt(
        self,
        thread_id: str,
        run_id: Optional[str] = None,
    ) -> bool:
        """
        人机协作中断

        Args:
            thread_id: 线程 ID
            run_id: 运行 ID

        Returns:
            bool: 是否成功中断
        """
        # 使用 LangGraph 的 update_state 实现中断
        # 这里需要获取 graph 实例，通过外部传入或缓存
        logger.info(f"Interrupt requested | thread={thread_id} run={run_id}")

        # 记录中断请求
        if run_id and run_id in self._active_executions:
            self._active_executions[run_id]["status"] = "interrupted"
            return True

        return False

    async def resume(
        self,
        graph: CompiledStateGraph,
        thread_id: str,
        values: dict,
        run_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        恢复中断

        Args:
            graph: 编译后的 LangGraph
            thread_id: 线程 ID
            values: 恢复时的值
            run_id: 运行 ID

        Returns:
            ExecutionResult: 执行结果
        """
        start_time = datetime.utcnow()
        run_id = run_id or str(uuid4())
        config = await self._build_config(thread_id, run_id)

        try:
            # 使用 LangGraph 的 ainvoke 恢复
            result = await graph.ainvoke(values, config=config)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # 清除中断状态
            if run_id in self._active_executions:
                del self._active_executions[run_id]

            return ExecutionResult.ok(result, duration_ms, {"run_id": run_id, "resumed": True})

        except Exception as e:
            logger.exception(f"Resume failed | run={run_id}")
            return ExecutionResult.error(str(e))

    async def get_state(
        self,
        graph: CompiledStateGraph,
        thread_id: str,
    ) -> Optional[dict]:
        """
        获取状态快照 (时间旅行)

        Args:
            graph: 编译后的 LangGraph
            thread_id: 线程 ID

        Returns:
            dict: 状态快照
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = await graph.aget_state(config)
            return state.values if state else None
        except Exception as e:
            logger.error(f"Get state failed | thread={thread_id} error={e}")
            return None

    async def patch_state(
        self,
        graph: CompiledStateGraph,
        thread_id: str,
        values: dict,
    ) -> bool:
        """
        修补状态 (时间旅行修改)

        Args:
            graph: 编译后的 LangGraph
            thread_id: 线程 ID
            values: 要修补的值

        Returns:
            bool: 是否成功
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            await graph.aupdate_state(config, values)
            return True
        except Exception as e:
            logger.error(f"Patch state failed | thread={thread_id} error={e}")
            return False

    async def _build_config(
        self,
        thread_id: str,
        run_id: str,
        callbacks: Optional[list] = None,
    ) -> RunnableConfig:
        """构建 LangGraph 配置"""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "run_id": run_id,
            },
            "recursion_limit": self.config.recursion_limit,
        }

        # 如果有检查点
        if self.checkpointer and self.config.checkpointer != "none":
            config["configurable"]["checkpoint_saver"] = self.checkpointer

        # 如果有中断配置
        if self.config.interrupt_before:
            config["interrupt_before"] = self.config.interrupt_before
        if self.config.interrupt_after:
            config["interrupt_after"] = self.config.interrupt_after

        # 添加回调
        if callbacks:
            config["callbacks"] = callbacks

        return config

    def _format_event(
        self,
        event: Any,
        metadata: dict,
        run_id: str,
    ) -> Dict[str, Any]:
        """格式化流式事件

        前端事件契约：
        - 助手内容以 {type: "token", content: "..."} 事件流式下发
        - {type: "complete"} 结束、{type: "error"} 错误
        """
        from langchain_core.messages import BaseMessage, AIMessage

        # 助手消息 → token 事件，供前端流式累积
        if isinstance(event, AIMessage):
            content = event.content or ""
            return {
                "type": "token",
                "run_id": run_id,
                "content": content,
            }

        # 其他 LangChain 消息对象
        if isinstance(event, BaseMessage):
            return {
                "type": "token",
                "run_id": run_id,
                "content": getattr(event, "content", str(event)) or "",
            }

        # dict 事件
        if isinstance(event, dict):
            return {
                "type": event.get("type", "unknown"),
                "run_id": run_id,
                **event,
            }

        # 带 type 属性的对象
        if hasattr(event, 'type'):
            return {
                "type": event.type,
                "run_id": run_id,
                "data": event,
                "metadata": metadata,
            }

        # 其他内容片段
        return {
            "type": "token",
            "run_id": run_id,
            "content": str(event),
        }

    def _record_execution(
        self,
        run_id: str,
        status: str,
        result: Optional[Any],
    ):
        """记录执行状态"""
        if status == "running":
            self._active_executions[run_id] = {
                "status": "running",
                "started_at": datetime.utcnow(),
            }
        elif status == "completed":
            if run_id in self._active_executions:
                self._active_executions[run_id]["status"] = "completed"
                self._active_executions[run_id]["completed_at"] = datetime.utcnow()
        elif status == "failed":
            if run_id in self._active_executions:
                self._active_executions[run_id]["status"] = "failed"
        elif status == "timeout":
            if run_id in self._active_executions:
                self._active_executions[run_id]["status"] = "timeout"
        elif status == "interrupted":
            if run_id in self._active_executions:
                self._active_executions[run_id]["status"] = "interrupted"

    def get_active_executions(self) -> List[Dict[str, Any]]:
        """获取所有活跃执行"""
        return [
            {"run_id": run_id, **info}
            for run_id, info in self._active_executions.items()
        ]


# 便捷函数

async def create_runtime(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    config: Optional[RuntimeConfig] = None,
) -> AgentRuntime:
    """创建 AgentRuntime 实例"""
    return AgentRuntime(checkpointer=checkpointer, config=config)
