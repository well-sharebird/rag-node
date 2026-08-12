"""主从编排 API - 主 Agent 编排 + 子 Agent 执行入口"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.orchestrator.graph import OrchestratorRuntime

router = APIRouter(prefix="/agents", tags=["agents-orchestrator"])


class OrchestratorRequest(BaseModel):
    query: str = Field(..., min_length=1)
    model_name: Optional[str] = None
    main_prompt: Optional[str] = None
    run_mode: str = Field("serial", pattern="^(serial|parallel)$")


@router.post("/execute/orchestrator")
async def execute_orchestrator(
    data: OrchestratorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """主从编排执行：主 Agent 决策 → 子 Agent 执行 → 聚合回答。
    返回 final_answer、sub_tasks、sub_agent_results。
    """
    runtime = OrchestratorRuntime(db, model_name=data.model_name)
    result = await runtime.run(
        query=data.query,
        main_prompt=data.main_prompt,
        run_mode=data.run_mode,
        user_id=current_user.id,
    )
    return result


class ExecuteAgentRequest(BaseModel):
    """确定性执行指定子 Agent 的请求（绕过主编排，直接执行该 Agent）"""
    query: str = Field(..., min_length=1)
    model_name: Optional[str] = None


@router.post("/{agent_id}/execute")
async def execute_agent_direct(
    agent_id: str,
    data: ExecuteAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """确定性执行指定 Agent（作为子任务独立运行）。

    绕过主 Agent 编排，直接加载并执行该 Agent——用于确定性验证，也让 meta/MCP
    的 execute_agent 具备公开 API。若触发 require_approval 敏感工具，返回 approvals。
    """
    from packages.agent.orchestrator.state import SubTask

    runtime = OrchestratorRuntime(db, model_name=data.model_name, user_id=current_user.id)
    sub_task = SubTask(sub_agent_id=agent_id, task_prompt=data.query)
    llm = await runtime._create_llm()
    res = await runtime._exec_sub_task(llm, sub_task, "你是通用助手。")
    return {
        "sub_agent_id": res.sub_agent_id,
        "success": res.success,
        "content": res.content,
        "approvals": res.approvals,
    }

