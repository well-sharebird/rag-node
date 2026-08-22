"""编排层数据访问仓库：隔离 OrchestratorRuntime 与存储细节（Repository 模式）。

把会话记忆读写与执行追踪落库从 OrchestratorRuntime（编排）中拆出，
让运行时只保留流程编排，数据访问收敛到专注的仓库对象。
"""
import json as _json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.models.conversation import Conversation, ConversationMessage

logger = logging.getLogger(__name__)


class ConversationRepository:
    """会话记忆读写（记忆回灌 / 持久化，Harness 5 大核心-记忆）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(self, user_id: int, session_id: Optional[str], query: str,
                   final_output: str, agent_id: Optional[str] = None) -> None:
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

    async def load_history(self, user_id: int, session_id: Optional[str],
                           limit: int = 6) -> List[Any]:
        """读取会话历史（记忆回灌）：返回 LangChain 消息序列（旧→新）。

        通过 metadata_json.session_id 定位会话（与 save 写入约定一致），
        仅取最近 N 轮，超长由 think 节点的 PromptAssembler 做 Token 预算压缩。
        """
        if not session_id:
            return []
        try:
            convs = (
                await self.db.execute(
                    select(Conversation)
                    .where(Conversation.user_id == user_id, Conversation.is_active.is_(True))
                    .order_by(Conversation.last_message_at.desc())
                    .limit(50)
                )
            ).scalars().all()
            target = None
            for c in convs:
                if not c.metadata_json:
                    continue
                try:
                    if (_json.loads(c.metadata_json) or {}).get("session_id") == session_id:
                        target = c
                        break
                except Exception:
                    continue
            if target is None:
                return []
            msgs = (
                await self.db.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == target.id)
                    .order_by(ConversationMessage.message_index.asc())
                    .limit(limit)
                )
            ).scalars().all()
            out: List[Any] = []
            for m in msgs:
                if m.role == "user":
                    out.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    out.append(AIMessage(content=m.content))
            return out[-limit:]
        except Exception as e:
            logger.warning("[Orchestrator] 会话历史读取失败: %s", e)
            return []


class ExecutionTraceRepository:
    """执行追踪落库（Harness 可观测性）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_trace(self, run_id: str, query: str, intent: str,
                         final_output: str, sub_agents: List[str], user_id: int,
                         sub_results: Optional[List[Dict]] = None) -> None:
        """记录一次执行追踪。

        sub_results（#8）：每条子 Agent 独立审计条目（id/success/content 摘要/
        error/approvals 数/thread_id），而非只记 id 列表。
        """
        try:
            from packages.agent.models.execution_trace import ExecutionTrace
            sub_entries = []
            for r in (sub_results or []):
                sub_entries.append({
                    "sub_agent_id": r.get("sub_agent_id"),
                    "success": bool(r.get("success")),
                    "content_summary": str(r.get("content") or "")[:300],
                    "error": r.get("error"),
                    "approval_count": len(r.get("approvals") or []),
                    "thread_id": (r.get("approvals") or [{}])[0].get("thread_id")
                    if r.get("approvals") else None,
                })
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
                steps=[{
                    "intent": intent,
                    "sub_agents": sub_agents,
                    "sub_agent_results": sub_entries,
                }],
                # 保留完整内容，不截断（数据库字段应使用 TEXT 类型）
                input_summary=query,
                output_summary=str(final_output) if final_output else None,
            )
            self.db.add(trace)
            await self.db.commit()
        except Exception as e:
            logger.warning("[Orchestrator] 执行追踪保存失败: %s", e)
            await self.db.rollback()
