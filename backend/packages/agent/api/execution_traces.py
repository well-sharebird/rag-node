"""
Execution Traces API - 执行追踪查询

提供执行历史的查询和分析能力
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from pydantic import BaseModel

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.models.execution_trace import ExecutionTrace

router = APIRouter(prefix="/execution-traces", tags=["execution-traces"])


# ============== Response Schemas ==============

class ExecutionTraceListItem(BaseModel):
    """执行追踪列表项"""
    id: str
    run_id: str
    agent_name: Optional[str]
    agent_type: Optional[str]
    status: str
    latency_ms: int
    total_tokens: int
    created_at: str


class ExecutionTraceDetail(BaseModel):
    """执行追踪详情"""
    id: str
    run_id: str
    thread_id: Optional[str]
    user_id: int
    tenant_id: Optional[str]
    agent_id: Optional[str]
    agent_name: Optional[str]
    agent_type: Optional[str]
    intent_type: Optional[str]
    status: str
    error_message: Optional[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    steps: list
    tool_calls: list
    input_summary: Optional[str]
    output_summary: Optional[str]
    created_at: str
    updated_at: str


class ExecutionSummary(BaseModel):
    """执行统计摘要"""
    period_days: int
    total_runs: int
    success_runs: int
    failed_runs: int
    success_rate: float
    avg_latency_ms: float
    total_tokens: int
    agent_type_distribution: dict


# ============== Helpers ==============

def trace_to_list_item(trace: ExecutionTrace) -> ExecutionTraceListItem:
    return ExecutionTraceListItem(
        id=str(trace.id),
        run_id=trace.run_id,
        agent_name=trace.agent_name,
        agent_type=trace.agent_type,
        status=trace.status,
        latency_ms=trace.latency_ms,
        total_tokens=trace.total_tokens,
        created_at=trace.created_at.isoformat() if trace.created_at else None,
    )


def trace_to_detail(trace: ExecutionTrace) -> ExecutionTraceDetail:
    return ExecutionTraceDetail(
        id=str(trace.id),
        run_id=trace.run_id,
        thread_id=trace.thread_id,
        user_id=trace.user_id,
        tenant_id=trace.tenant_id,
        agent_id=str(trace.agent_id) if trace.agent_id else None,
        agent_name=trace.agent_name,
        agent_type=trace.agent_type,
        intent_type=trace.intent_type,
        status=trace.status,
        error_message=trace.error_message,
        latency_ms=trace.latency_ms,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        total_tokens=trace.total_tokens,
        steps=trace.steps or [],
        tool_calls=trace.tool_calls or [],
        input_summary=trace.input_summary,
        output_summary=trace.output_summary,
        created_at=trace.created_at.isoformat() if trace.created_at else None,
        updated_at=trace.updated_at.isoformat() if trace.updated_at else None,
    )


# ============== API Endpoints ==============

@router.get("", response_model=List[ExecutionTraceListItem])
async def list_execution_traces(
    status: Optional[str] = Query(None, description="过滤状态：success, error, failed"),
    agent_type: Optional[str] = Query(None, description="过滤 Agent 类型：single, multi, meta"),
    days: int = Query(7, ge=1, le=30, description="查询最近 N 天"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询执行追踪列表

    - **status**: 过滤执行状态
    - **agent_type**: 过滤 Agent 类型
    - **days**: 查询最近 N 天的数据 (1-30)
    - **limit**: 返回数量限制
    - **offset**: 偏移量
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    conditions = [
        ExecutionTrace.user_id == current_user.id,
        ExecutionTrace.created_at >= cutoff_date,
    ]

    if status:
        conditions.append(ExecutionTrace.status == status)
    if agent_type:
        conditions.append(ExecutionTrace.agent_type == agent_type)

    result = await db.execute(
        select(ExecutionTrace)
        .where(*conditions)
        .order_by(ExecutionTrace.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    traces = result.scalars().all()
    return [trace_to_list_item(t) for t in traces]


@router.get("/{run_id}", response_model=ExecutionTraceDetail)
async def get_execution_trace(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个执行追踪详情

    - **run_id**: 执行运行 ID
    """
    result = await db.execute(
        select(ExecutionTrace)
        .where(
            ExecutionTrace.run_id == run_id,
            ExecutionTrace.user_id == current_user.id,
        )
    )

    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Execution trace not found")

    return trace_to_detail(trace)


@router.get("/stats/summary", response_model=ExecutionSummary)
async def get_execution_summary(
    days: int = Query(7, ge=1, le=30, description="统计最近 N 天"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取执行统计摘要

    返回:
    - 总执行次数
    - 成功/失败次数
    - 平均延迟
    - Token 使用统计
    - 各 Agent 类型分布
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # 基础统计
    result = await db.execute(
        select(
            func.count(ExecutionTrace.id),
            func.sum(func.case((ExecutionTrace.status == "success", 1), else_=0)),
            func.sum(func.case((ExecutionTrace.status != "success", 1), else_=0)),
            func.avg(ExecutionTrace.latency_ms),
            func.sum(ExecutionTrace.total_tokens),
        )
        .where(
            ExecutionTrace.user_id == current_user.id,
            ExecutionTrace.created_at >= cutoff_date,
        )
    )

    row = result.first()
    total_runs = row[0] or 0
    success_runs = row[1] or 0
    failed_runs = row[2] or 0
    avg_latency = float(row[3]) if row[3] else 0
    total_tokens = row[4] or 0

    # Agent 类型分布
    agent_type_result = await db.execute(
        select(
            ExecutionTrace.agent_type,
            func.count(ExecutionTrace.id),
        )
        .where(
            ExecutionTrace.user_id == current_user.id,
            ExecutionTrace.created_at >= cutoff_date,
        )
        .group_by(ExecutionTrace.agent_type)
    )

    agent_type_distribution = {
        row.agent_type: row.count
        for row in agent_type_result.all()
    }

    return ExecutionSummary(
        period_days=days,
        total_runs=total_runs,
        success_runs=success_runs,
        failed_runs=failed_runs,
        success_rate=round(success_runs / total_runs * 100, 2) if total_runs > 0 else 0,
        avg_latency_ms=round(avg_latency, 2),
        total_tokens=total_tokens,
        agent_type_distribution=agent_type_distribution,
    )
