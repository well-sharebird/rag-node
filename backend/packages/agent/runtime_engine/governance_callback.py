"""
Governance Callback - 基于 LangGraph Callback 的管控层

将 Governance Engine 从独立追踪重构为 LangGraph 的 AsyncCallbackHandler

核心能力:
1. 全链路追踪 - 通过 Callback 自动记录
2. 合规检查 - 执行前后检查
3. 异常检测 - 识别可疑行为
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from uuid import uuid4

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult, ChatGenerationChunk

logger = logging.getLogger(__name__)


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: str
    action: str
    timestamp: str
    duration_ms: int
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class GovernanceCallbackHandler(AsyncCallbackHandler):
    """
    Governance 回调处理器

    通过 LangGraph Callback 机制实现无侵入式追踪:
    - on_llm_start/end - LLM 调用追踪
    - on_tool_start/end - 工具调用追踪
    - on_chain_start/end - 链式调用追踪
    """

    def __init__(
        self,
        trace_id: str,
        engine: Optional["GovernanceEngine"] = None,
    ):
        self.trace_id = trace_id
        self.engine = engine or GovernanceEngine()
        self._start_times: Dict[str, datetime] = {}
        self._current_step: Optional[str] = None

    async def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        """LLM 调用开始"""
        step_id = f"llm_{uuid4().hex[:8]}"
        self._start_times[step_id] = datetime.utcnow()
        self._current_step = step_id

        logger.info(f"[Trace:{self.trace_id}] LLM call started | step={step_id}")

    async def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束"""
        if self._current_step and self._current_step in self._start_times:
            duration_ms = int(
                (datetime.utcnow() - self._start_times[self._current_step]).total_seconds() * 1000
            )

            # 提取 Token 使用
            token_usage = {}
            if response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})

            await self.engine.add_step(
                self.trace_id,
                ExecutionStep(
                    step_id=self._current_step,
                    action="llm_call",
                    timestamp=datetime.utcnow().isoformat(),
                    duration_ms=duration_ms,
                    metadata={
                        "token_usage": token_usage,
                        "generation_count": len(response.generations) if response.generations else 0,
                    },
                ),
            )

            logger.info(f"[Trace:{self.trace_id}] LLM call ended | step={self._current_step} duration={duration_ms}ms")

            self._current_step = None

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """工具调用开始"""
        step_id = f"tool_{uuid4().hex[:8]}"
        self._start_times[step_id] = datetime.utcnow()
        self._current_step = step_id

        tool_name = serialized.get("name", "unknown")
        logger.info(f"[Trace:{self.trace_id}] Tool call started | step={step_id} tool={tool_name}")

    async def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> None:
        """工具调用结束"""
        if self._current_step and self._current_step in self._start_times:
            duration_ms = int(
                (datetime.utcnow() - self._start_times[self._current_step]).total_seconds() * 1000
            )

            await self.engine.add_step(
                self.trace_id,
                ExecutionStep(
                    step_id=self._current_step,
                    action="tool_call",
                    timestamp=datetime.utcnow().isoformat(),
                    duration_ms=duration_ms,
                    metadata={"output": output[:500] if len(output) > 500 else output},
                ),
            )

            logger.info(f"[Trace:{self.trace_id}] Tool call ended | step={self._current_step} duration={duration_ms}ms")

            self._current_step = None

    async def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """链式调用开始"""
        step_id = f"chain_{uuid4().hex[:8]}"
        self._start_times[step_id] = datetime.utcnow()
        self._current_step = step_id

        chain_name = serialized.get("name", "unknown")
        logger.info(f"[Trace:{self.trace_id}] Chain started | step={step_id} chain={chain_name}")

    async def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """链式调用结束"""
        if self._current_step and self._current_step in self._start_times:
            duration_ms = int(
                (datetime.utcnow() - self._start_times[self._current_step]).total_seconds() * 1000
            )

            await self.engine.add_step(
                self.trace_id,
                ExecutionStep(
                    step_id=self._current_step,
                    action="chain_call",
                    timestamp=datetime.utcnow().isoformat(),
                    duration_ms=duration_ms,
                    metadata={"outputs": outputs},
                ),
            )

            logger.info(f"[Trace:{self.trace_id}] Chain ended | step={self._current_step} duration={duration_ms}ms")

            self._current_step = None

    async def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        **kwargs: Any,
    ) -> None:
        """检索开始"""
        step_id = f"retriever_{uuid4().hex[:8]}"
        self._start_times[step_id] = datetime.utcnow()
        logger.info(f"[Trace:{self.trace_id}] Retriever started | step={step_id}")

    async def on_retriever_end(
        self,
        documents: List[Any],
        **kwargs: Any,
    ) -> None:
        """检索结束"""
        if self._current_step and self._current_step in self._start_times:
            duration_ms = int(
                (datetime.utcnow() - self._start_times[self._current_step]).total_seconds() * 1000
            )

            await self.engine.add_step(
                self.trace_id,
                ExecutionStep(
                    step_id=self._current_step,
                    action="retriever_call",
                    timestamp=datetime.utcnow().isoformat(),
                    duration_ms=duration_ms,
                    metadata={"document_count": len(documents)},
                ),
            )

            logger.info(f"[Trace:{self.trace_id}] Retriever ended | step={self._current_step}")

    async def on_text(
        self,
        text: str,
        **kwargs: Any,
    ) -> None:
        """文本生成事件"""
        # 用于流式输出追踪
        pass

    async def on_agent_action(
        self,
        action: Any,
        **kwargs: Any,
    ) -> None:
        """Agent 行动"""
        logger.info(f"[Trace:{self.trace_id}] Agent action | action={action}")

    async def on_agent_finish(
        self,
        finish: Any,
        **kwargs: Any,
    ) -> None:
        """Agent 结束"""
        logger.info(f"[Trace:{self.trace_id}] Agent finished | finish={finish}")

    async def on_retry(
        self,
        retry_state: Any,
        **kwargs: Any,
    ) -> None:
        """重试事件"""
        logger.warning(f"[Trace:{self.trace_id}] Retry | state={retry_state}")

    async def on_custom_event(
        self,
        name: str,
        data: Any,
        **kwargs: Any,
    ) -> None:
        """自定义事件"""
        logger.info(f"[Trace:{self.trace_id}] Custom event | name={name}")


class GovernanceEngine:
    """
    管控引擎 - 基于 Callback 构建

    提供:
    1. 全链路追踪
    2. 合规检查
    3. 异常检测
    """

    def __init__(self):
        self._active_traces: Dict[str, List[ExecutionStep]] = {}

    def get_callback(self, trace_id: str) -> GovernanceCallbackHandler:
        """获取 Callback 处理器"""
        return GovernanceCallbackHandler(trace_id, self)

    async def start_trace(
        self,
        runtime_id: str,
        session_id: str,
        user_id: int,
    ) -> str:
        """开始追踪"""
        trace_id = f"trace_{uuid4().hex[:12]}"
        self._active_traces[trace_id] = []

        logger.info(f"Trace started: {trace_id} | runtime={runtime_id} session={session_id}")
        return trace_id

    async def add_step(
        self,
        trace_id: str,
        step: ExecutionStep,
    ) -> None:
        """添加执行步骤"""
        if trace_id not in self._active_traces:
            logger.warning(f"Trace not found: {trace_id}")
            return

        self._active_traces[trace_id].append(step)
        logger.debug(f"Step added to trace {trace_id}: {step.action}")

    async def complete_trace(
        self,
        trace_id: str,
        status: str = "completed",
    ) -> List[ExecutionStep]:
        """完成追踪"""
        if trace_id not in self._active_traces:
            logger.warning(f"Trace not found: {trace_id}")
            return []

        steps = self._active_traces.pop(trace_id)

        # 计算总耗时
        total_duration_ms = sum(s.duration_ms for s in steps)

        logger.info(
            f"Trace completed: {trace_id} | status={status} "
            f"steps={len(steps)} duration={total_duration_ms}ms"
        )

        return steps

    async def check_compliance(
        self,
        trace_id: str,
        steps: List[ExecutionStep],
    ) -> Dict[str, Any]:
        """
        合规检查

        检查执行过程是否符合策略
        """
        checks = []

        # 检查 1: 危险操作
        dangerous_actions = self._check_dangerous_actions(steps)
        checks.append({
            "name": "dangerous_action_check",
            "passed": not dangerous_actions,
            "details": dangerous_actions or "No dangerous actions",
        })

        # 检查 2: 速率限制
        rate_violations = self._check_rate_limit_violations(steps)
        checks.append({
            "name": "rate_limit_check",
            "passed": not rate_violations,
            "details": rate_violations or "No rate violations",
        })

        overall_passed = all(c["passed"] for c in checks)

        return {
            "trace_id": trace_id,
            "overall_passed": overall_passed,
            "checks": checks,
            "score": sum(1 for c in checks if c["passed"]) / len(checks) * 100 if checks else 0,
        }

    def _check_dangerous_actions(self, steps: List[ExecutionStep]) -> Optional[str]:
        """检查危险操作"""
        dangerous_patterns = [
            "delete_all",
            "drop_table",
            "rm -rf",
            "sudo",
            "chmod 777",
        ]

        for step in steps:
            step_str = json.dumps(step.metadata or {}).lower()
            for pattern in dangerous_patterns:
                if pattern in step_str:
                    return f"Dangerous pattern: {pattern}"

        return None

    def _check_rate_limit_violations(self, steps: List[ExecutionStep]) -> Optional[str]:
        """检查速率限制违规"""
        # 简化实现：检查是否有大量重复操作
        action_counts: Dict[str, int] = {}
        for step in steps:
            action = step.action
            action_counts[action] = action_counts.get(action, 0) + 1

        for action_type, count in action_counts.items():
            if count > 100:
                return f"Rate limit exceeded for {action_type}: {count} times"

        return None

    def get_trace(self, trace_id: str) -> Optional[List[ExecutionStep]]:
        """获取追踪记录"""
        return self._active_traces.get(trace_id)

    def get_all_traces(self) -> Dict[str, List[ExecutionStep]]:
        """获取所有活跃追踪"""
        return dict(self._active_traces)


# ============================================================
# 便捷函数
# ============================================================

def create_governance_callback(
    trace_id: str,
    engine: Optional[GovernanceEngine] = None,
) -> GovernanceCallbackHandler:
    """创建 Governance Callback"""
    return GovernanceCallbackHandler(trace_id, engine or GovernanceEngine())
