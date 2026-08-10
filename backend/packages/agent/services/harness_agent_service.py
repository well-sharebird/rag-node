"""
Harness Agent Service - 基于 Harness 架构的 Agent 服务

三层架构:
- Harness 层：业务语义 (HarnessEngine)
- Runtime 层：执行引擎 (AgentRuntime)
- Framework 层：LangGraph 组件 (TAO Graph, Orchestration Graph)
"""
import logging
import time
import json
from typing import Optional, Any, AsyncGenerator, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.models.agent import AgentConfig, AgentCallLog
from packages.agent.harness import HarnessEngine, HarnessConfig as HarnessBusinessConfig
from packages.agent.harness.config import CollaborationMode
from packages.agent.services.agent_memory_service import AgentMemoryService
from packages.agent.services.conversation_service import create_or_update_conversation_from_agent

logger = logging.getLogger("app.services.harness_agent_service")


def _safe_json_default(obj: Any) -> Any:
    """LangChain 流式事件的 JSON 安全序列化处理器"""
    from langchain_core.messages import BaseMessage

    if isinstance(obj, BaseMessage):
        return {
            "role": getattr(obj, "type", "unknown"),
            "content": getattr(obj, "content", str(obj)),
            "tool_calls": getattr(obj, "tool_calls", []) or [],
        }
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    # 枚举等
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_safe_json_default)


class HarnessAgentService:
    """
    Harness Agent 服务 - 基于 Harness 架构
    """

    def __init__(
        self,
        db: AsyncSession,
        model_gateway: Any,
        skill_registry: Any,
    ):
        self.db = db
        self.model_gateway = model_gateway
        self.skill_registry = skill_registry
        self._harness_engine = self._create_harness_engine()

    def _create_harness_engine(self) -> HarnessEngine:
        """创建 HarnessEngine"""
        harness_config = HarnessBusinessConfig(
            runtime=None,  # 使用默认 RuntimeConfig
            enable_planning_tools=False,
            enable_rag_tools=True,
            collaboration_modes=[
                CollaborationMode.SUPERVISOR,
                CollaborationMode.ROUND_ROBIN,
                CollaborationMode.VOTING,
            ],
        )

        return HarnessEngine(
            db=self.db,
            config=harness_config,
        )

    async def execute(
        self,
        agent_id: Optional[str],
        query: str,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> "HarnessAgentExecuteResult":
        """
        执行 Agent - Harness 架构

        执行逻辑:
        1. 未指定 agent_id → 使用 Meta Agent 自主决策
        2. 指定 agent_id → 根据 AgentConfig.agent_type 决定
           - agent_type == "multi" → 多智能体协作
           - 其他 → 单智能体执行
        """
        start_time = time.time()
        run_id = f"{user_id}_{int(time.time() * 1000)}"

        logger.info(
            "[HarnessAgentService] Starting execution | run=%s agent=%s user=%s",
            run_id, agent_id, user_id
        )

        # 根据是否指定 agent_id 选择执行路径
        if not agent_id:
            result = await self._execute_meta(
                query=query,
                user_id=user_id,
                tenant_id=tenant_id,
                kb_ids=kb_ids,
                top_k=top_k,
                enable_rerank=enable_rerank,
                model_name=model_name,
                session_id=session_id,
                run_id=run_id,
            )
        else:
            agent_config = await self.db.execute(
                select(AgentConfig).where(AgentConfig.id == agent_id)
            )
            agent_config_obj = agent_config.scalar_one_or_none()

            if agent_config_obj and agent_config_obj.agent_type == "multi":
                result = await self._execute_multi(
                    agent_id=agent_id,
                    query=query,
                    user_id=user_id,
                    session_id=session_id,
                    kb_ids=kb_ids,
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                    model_name=model_name,
                    run_id=run_id,
                )
            else:
                result = await self._execute_single(
                    agent_id=agent_id,
                    query=query,
                    user_id=user_id,
                    session_id=session_id,
                    kb_ids=kb_ids,
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                    model_name=model_name,
                    run_id=run_id,
                )

        latency_ms = int((time.time() - start_time) * 1000)
        await self._log_execution(
            agent_id=agent_id,
            user_id=user_id,
            run_id=run_id,
            latency_ms=latency_ms,
            result=result,
        )

        # 保存会话
        await self._save_conversation(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            query=query,
            response=result.response,
            kb_ids=kb_ids,
        )

        return result

    async def execute_stream(
        self,
        agent_id: Optional[str],
        query: str,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 Agent - Harness 架构
        """
        run_id = f"{user_id}_{int(time.time() * 1000)}"
        start_time = time.time()

        logger.info(
            "[HarnessAgentService] Starting stream execution | run=%s agent=%s user=%s",
            run_id, agent_id, user_id
        )

        try:
            if not agent_id:
                async for chunk in self._execute_meta_stream(
                    query=query,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    kb_ids=kb_ids,
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                    model_name=model_name,
                    session_id=session_id,
                    run_id=run_id,
                ):
                    yield chunk
            else:
                agent_config = await self.db.execute(
                    select(AgentConfig).where(AgentConfig.id == agent_id)
                )
                agent_config_obj = agent_config.scalar_one_or_none()

                if agent_config_obj and agent_config_obj.agent_type == "multi":
                    async for chunk in self._execute_multi_stream(
                        agent_id=agent_id,
                        query=query,
                        user_id=user_id,
                        session_id=session_id,
                        kb_ids=kb_ids,
                        top_k=top_k,
                        enable_rerank=enable_rerank,
                        model_name=model_name,
                        run_id=run_id,
                    ):
                        yield chunk
                else:
                    async for chunk in self._execute_single_stream(
                        agent_id=agent_id,
                        query=query,
                        user_id=user_id,
                        session_id=session_id,
                        kb_ids=kb_ids,
                        top_k=top_k,
                        enable_rerank=enable_rerank,
                        model_name=model_name,
                        run_id=run_id,
                    ):
                        yield chunk

            latency_ms = int((time.time() - start_time) * 1000)
            yield _safe_json_dumps({
                "type": "complete",
                "data": {"run_id": run_id, "latency_ms": latency_ms}
            })

            # 保存会话
            await self._save_conversation(
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
                query=query,
                response="",  # 流式模式下在客户端累积
                kb_ids=kb_ids,
            )

        except Exception as e:
            logger.exception("[HarnessAgentService] Stream execution failed | run=%s", run_id)
            yield _safe_json_dumps({
                "type": "error",
                "data": {"error": str(e)}
            })

    # ============================================================
    # 单智能体执行
    # ============================================================

    async def _execute_single(
        self,
        agent_id: str,
        query: str,
        user_id: int,
        session_id: Optional[str],
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> "HarnessAgentExecuteResult":
        """执行单个智能体"""
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        harness_result = await self._harness_engine.execute(
            query=query,
            agent_id=agent_id,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
        )

        return HarnessAgentExecuteResult(
            run_id=run_id or "unknown",
            agent_id=agent_id,
            response=str(harness_result.result) if harness_result.result else "",
            messages=[],
            agents_used=[],
            latency_ms=harness_result.duration_ms,
        )

    async def _execute_single_stream(
        self,
        agent_id: str,
        query: str,
        user_id: int,
        session_id: Optional[str],
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式执行单个智能体"""
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        async for event in self._harness_engine.execute_stream(
            query=query,
            agent_id=agent_id,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            model_name=model_name,
        ):
            yield _safe_json_dumps(event)

    # ============================================================
    # 多智能体执行
    # ============================================================

    async def _execute_multi(
        self,
        agent_id: str,
        query: str,
        user_id: int,
        session_id: Optional[str],
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> "HarnessAgentExecuteResult":
        """执行多智能体协作"""
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        harness_result = await self._harness_engine.execute(
            query=query,
            agent_id=agent_id,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
        )

        return HarnessAgentExecuteResult(
            run_id=run_id or "unknown",
            agent_id=agent_id,
            response=str(harness_result.result) if harness_result.result else "",
            messages=[],
            agents_used=[],
            latency_ms=harness_result.duration_ms,
        )

    async def _execute_multi_stream(
        self,
        agent_id: str,
        query: str,
        user_id: int,
        session_id: Optional[str],
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式执行多智能体协作"""
        thread_id = f"{user_id}:{agent_id}:{session_id or 'default'}"

        async for event in self._harness_engine.execute_stream(
            query=query,
            agent_id=agent_id,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            model_name=model_name,
        ):
            yield _safe_json_dumps(event)

    # ============================================================
    # Meta Agent 执行
    # ============================================================

    async def _execute_meta(
        self,
        query: str,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> "HarnessAgentExecuteResult":
        """执行 Meta Agent"""
        thread_id = f"{user_id}:meta:{session_id or 'default'}"

        harness_result = await self._harness_engine.execute(
            query=query,
            agent_id=None,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        return HarnessAgentExecuteResult(
            run_id=run_id or "unknown",
            agent_id=None,
            response=str(harness_result.result) if harness_result.result else "",
            messages=[],
            agents_used=[],
            latency_ms=harness_result.duration_ms,
        )

    async def _execute_meta_stream(
        self,
        query: str,
        user_id: int,
        tenant_id: str,
        kb_ids: Optional[List[str]] = None,
        top_k: int = 5,
        enable_rerank: bool = False,
        model_name: Optional[str] = None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式执行 Meta Agent"""
        thread_id = f"{user_id}:meta:{session_id or 'default'}"

        async for event in self._harness_engine.execute_stream(
            query=query,
            agent_id=None,
            thread_id=thread_id,
            kb_ids=kb_ids,
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            tenant_id=tenant_id,
            model_name=model_name,
        ):
            yield _safe_json_dumps(event)

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _save_conversation(
        self,
        user_id: int,
        agent_id: Optional[str],
        session_id: Optional[str],
        query: str,
        response: str,
        kb_ids: Optional[List[str]] = None,
    ) -> None:
        """保存会话到 conversations 表"""
        try:
            session_id = session_id or f"session_{int(time.time() * 1000)}"
            messages = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": response},
            ]

            await create_or_update_conversation_from_agent(
                db=self.db,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
                title=query[:50] if query else "New conversation",
                messages=messages,
                kb_ids=kb_ids,
            )

            logger.info(
                "[HarnessAgentService] Conversation saved | user=%s session=%s",
                user_id, session_id
            )
        except Exception as e:
            logger.warning("[HarnessAgentService] Failed to save conversation: %s", e)

    async def _log_execution(
        self,
        agent_id: Optional[str],
        user_id: int,
        run_id: str,
        latency_ms: int,
        result: "HarnessAgentExecuteResult",
    ) -> None:
        """记录调用日志"""
        try:
            call_log = AgentCallLog(
                agent_id=agent_id or "00000000-0000-0000-0000-000000000000",
                run_id=run_id,
                user_id=user_id,
                thread_id=f"{user_id}:{agent_id or 'meta'}:default",
                input_summary={"query": result.response[:500] if result.response else ""},
                output_summary={"response": result.response[:500] if result.response else ""},
                latency_ms=latency_ms,
                status="success",
            )

            self.db.add(call_log)
            await self.db.commit()

            logger.info(
                "[HarnessAgentService] Execution logged | run=%s agent=%s latency=%dms",
                run_id, agent_id, latency_ms
            )
        except Exception as e:
            logger.warning("[HarnessAgentService] Failed to log execution | run=%s error=%s", run_id, e)


class HarnessAgentExecuteResult:
    """Harness Agent 执行结果"""

    def __init__(
        self,
        run_id: str,
        agent_id: Optional[str],
        response: str,
        messages: List[Any] = None,
        agents_used: List[str] = None,
        latency_ms: int = 0,
        tokens_used: int = 0,
        metadata: Optional[Dict] = None,
    ):
        self.run_id = run_id
        self.agent_id = agent_id
        self.response = response
        self.messages = messages or []
        self.agents_used = agents_used or []
        self.latency_ms = latency_ms
        self.tokens_used = tokens_used
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "response": self.response,
            "messages": self.messages,
            "agents_used": self.agents_used,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
        }


async def create_harness_agent_service(
    db: AsyncSession,
    model_gateway: Any,
    skill_registry: Any,
) -> HarnessAgentService:
    """创建 HarnessAgentService 实例"""
    return HarnessAgentService(
        db=db,
        model_gateway=model_gateway,
        skill_registry=skill_registry,
    )
