"""通用 LangGraph 运行时门面（Facade）。

把"怎么跟一个编译好的 LangGraph 对话"——执行/流式/断点恢复/状态快照/修补/
中断 + checkpointer/配置/token 预算压缩/重试——从 OrchestratorRuntime 中独立出来。
它与具体业务（主 Agent 编排）无关，可复用于任意图；OrchestratorRuntime 继承它，
作为"具备完整图执行能力的编排运行时"。对应三层铁律的运行时增强层。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from packages.agent.core.harness.config import RuntimeConfig
from packages.agent.runtime_engine.state import ExecutionResult

logger = logging.getLogger(__name__)


class GraphRuntime:
    """通用图执行原语：上下文压缩 + checkpointer + 重试 + 硬超时 + 状态/中断。"""

    def __init__(self, config: Optional[RuntimeConfig] = None):
        self.config = config or RuntimeConfig()
        self._checkpointer = None  # 惰性初始化（断点持久化）

    def _get_checkpointer(self):
        """惰性创建数据库 checkpointer（断点/会话恢复，Harness 运行时增强）。"""
        if self._checkpointer is None:
            try:
                from packages.agent.runtime_engine.checkpointer import create_async_checkpointer
                self._checkpointer = create_async_checkpointer()
            except Exception as e:
                logger.warning("[GraphRuntime] checkpointer 初始化失败: %s", e)
                self._checkpointer = None
        return self._checkpointer

    def _build_config(self, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None) -> dict:
        """构建 LangGraph 配置：thread_id/递归上限/checkpointer/中断/回调。"""
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.config.recursion_limit,
        }
        if run_id:
            config["configurable"]["run_id"] = run_id
        # 注：checkpoint_saver 仅在编译期绑定（_build_agent_graph(use_checkpointer=True)），
        # config 塞 configurable.checkpoint_saver 在现代 LangGraph 中无效，故不再注入。
        if self.config.interrupt_before:
            config["interrupt_before"] = self.config.interrupt_before
        if self.config.interrupt_after:
            config["interrupt_after"] = self.config.interrupt_after
        if callbacks:
            config["callbacks"] = callbacks
        return config

    @property
    def _compressor(self):
        from packages.agent.core.harness.context import ContextCompressor
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
        from packages.agent.core.harness.security.retry import RetryPolicy
        return RetryPolicy(
            max_retries=self.config.max_retries,
            delay_seconds=self.config.retry_delay_seconds,
        )

    # ---------------- 执行（批量）----------------
    async def execute(self, graph, state: dict, thread_id: str, run_id: Optional[str] = None,
                      callbacks: Optional[list] = None) -> ExecutionResult:
        """批量执行给定编译图：上下文压缩 + 重试 + 硬超时。"""
        from packages.agent.core.harness.security.retry import with_retry
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

    # ---------------- 状态 / 断点 / 中断（时间旅行 + HITL）----------------
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
        from packages.agent.core.harness.security.retry import with_retry
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
