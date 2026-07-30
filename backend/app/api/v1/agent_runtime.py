"""
Agent 运行时 API
支持用户选择模型并执行 Agent
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.agent import AgentConfig
from app.schemas.chat import (
    AgentRunRequest,
    AgentRunResponse,
    ModelConfig,
    AgentStreamEvent,
)
from app.services.agent_runtime_service import AgentRuntime
from app.services.model_gateway_service import ModelGatewayService
from app.services.skill_registry import SkillRegistry

router = APIRouter(prefix="/agents", tags=["agents-runtime"])


def get_agent_runtime(db: AsyncSession) -> AgentRuntime:
    """获取 Agent Runtime 实例"""
    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistry(db)
    return AgentRuntime(
        db=db,
        model_gateway_service=model_gateway,
        skill_registry=skill_registry,
    )


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行 Agent（非流式）

    用户在运行时选择模型，传递给 Agent 执行
    """
    runtime = get_agent_runtime(db)

    # 验证 Agent 存在且有权限访问
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 检查权限：只能运行自己的 Agent 或公开的 Agent
    if agent.user_id != current_user.id and not agent.is_public:
        raise HTTPException(status_code=403, detail="No permission to run this agent")

    try:
        result = await runtime.run(
            agent_id=request.agent_id,
            user_id=current_user.id,
            query=request.query,
            model_config=request.model,
            session_id=request.session_id,
        )

        return AgentRunResponse(
            run_id=result["run_id"],
            agent_id=request.agent_id,
            response=result["response"],
            model_used=request.model.model,
            input_tokens=0,  # TODO: 从 result 中获取
            output_tokens=0,
            latency_ms=0,
            session_id=request.session_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")


@router.post("/run/stream")
async def run_agent_stream(
    request: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行 Agent（流式）

    用户在运行时选择模型，SSE 流式返回结果
    """
    runtime = get_agent_runtime(db)

    # 验证 Agent 存在且有权限访问
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 检查权限
    if agent.user_id != current_user.id and not agent.is_public:
        raise HTTPException(status_code=403, detail="No permission to run this agent")

    async def generate_events():
        """生成 SSE 事件"""
        try:
            async for token in runtime.run_stream(
                agent_id=request.agent_id,
                user_id=current_user.id,
                query=request.query,
                model_config=request.model,
                session_id=request.session_id,
            ):
                # EventSourceResponse 需要 event 和 data 字段
                yield {
                    "event": "message",
                    "data": AgentStreamEvent(type="token", content=token).model_dump_json(),
                }

            # 结束事件
            yield {
                "event": "message",
                "data": AgentStreamEvent(type="done").model_dump_json(),
            }

        except Exception as e:
            yield {
                "event": "message",
                "data": AgentStreamEvent(type="error", error=str(e)).model_dump_json(),
            }

    return EventSourceResponse(
        generate_events(),
        media_type="text/event-stream",
    )


@router.post("/{agent_id}/memory/clear")
async def clear_agent_memory(
    agent_id: str,
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除 Agent 的会话记忆"""
    runtime = get_agent_runtime(db)

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    await runtime.clear_memory(agent_id, current_user.id, session_id)
    return {"message": "Memory cleared"}


@router.get("/{agent_id}/memory")
async def get_agent_memory(
    agent_id: str,
    session_id: str = Query(..., description="会话 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 Agent 的对话历史"""
    from app.services.agent_memory_service import AgentMemoryService

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    memory_service = AgentMemoryService(db)
    thread_id = f"{current_user.id}:{agent_id}:{session_id}"
    messages = await memory_service.get_conversation(agent_id, current_user.id, thread_id)

    return {"messages": messages}
