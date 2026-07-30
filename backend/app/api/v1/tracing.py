"""
执行追踪 API
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.models.user import User
from app.services.trace_service import TraceService, get_es_client

router = APIRouter(prefix="/tracing", tags=["tracing"])


# ============ Response Models ============

class TraceSpanResponse(BaseModel):
    """单个跨度响应"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    execution_type: str
    execution_id: str
    node_type: str
    node_name: str
    status: str
    duration_ms: Optional[int]
    started_at: str
    completed_at: Optional[str]
    input_data: Optional[dict]
    output_data: Optional[dict]
    error_info: Optional[dict]


class TraceTreeResponse(BaseModel):
    """追踪树响应"""
    trace_id: str
    execution_type: str
    execution_id: str
    total_spans: int
    total_duration_ms: int
    final_status: str
    started_at: str
    completed_at: str
    spans: List[TraceSpanResponse]


class TraceListItemResponse(BaseModel):
    """追踪列表项响应"""
    trace_id: str
    execution_type: str
    execution_id: str
    total_spans: int
    total_duration_ms: int
    final_status: str
    started_at: str
    completed_at: str


class TraceListResponse(BaseModel):
    """追踪列表响应"""
    traces: List[TraceListItemResponse]
    next_search_after: Optional[list]
    has_more: bool


class TraceStatsResponse(BaseModel):
    """追踪统计响应"""
    span_count: int
    avg_duration: Optional[float]
    total_duration: int
    status_breakdown: dict
    final_status: str


class TraceDurationBreakdownResponse(BaseModel):
    """耗时分析响应"""
    node_type: str
    node_name: str
    duration_ms: Optional[int]
    status: str


# ============ Query Models ============

class TraceListRequest(BaseModel):
    """追踪列表查询请求"""
    execution_type: Optional[str] = Field(None, description="执行类型")
    execution_id: Optional[str] = Field(None, description="执行 ID")
    status: Optional[str] = Field(None, description="状态")
    start_time: Optional[str] = Field(None, description="开始时间 (ISO 格式)")
    end_time: Optional[str] = Field(None, description="结束时间 (ISO 格式)")
    user_id: Optional[int] = Field(None, description="用户 ID")
    search_after: Optional[list] = Field(None, description="分页游标")
    size: int = Field(20, ge=1, le=100, description="每页大小")


# ============ API Endpoints ============

@router.get("/{trace_id}", response_model=TraceTreeResponse)
async def get_trace_tree(
    trace_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取追踪树详情

    返回完整的执行追踪树，包括所有跨度的输入输出
    """
    es = get_es_client()
    service = TraceService(es)

    # 获取追踪树
    spans = await service.get_trace_tree(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")

    # 获取统计信息
    stats = await service.get_trace_stats(trace_id)

    return TraceTreeResponse(
        trace_id=trace_id,
        execution_type=spans[0].get("execution_type", "unknown"),
        execution_id=spans[0].get("execution_id", "unknown"),
        total_spans=len(spans),
        total_duration_ms=stats.get("total_duration", 0),
        final_status=stats.get("final_status", "unknown"),
        started_at=spans[0].get("started_at", ""),
        completed_at=spans[-1].get("completed_at", ""),
        spans=[
            TraceSpanResponse(
                trace_id=s["trace_id"],
                span_id=s["span_id"],
                parent_span_id=s.get("parent_span_id"),
                execution_type=s["execution_type"],
                execution_id=s["execution_id"],
                node_type=s["node_type"],
                node_name=s["node_name"],
                status=s["status"],
                duration_ms=s.get("duration_ms"),
                started_at=s["started_at"],
                completed_at=s.get("completed_at"),
                input_data=s.get("input_data"),
                output_data=s.get("output_data"),
                error_info=s.get("error_info"),
            )
            for s in spans
        ],
    )


@router.post("/list", response_model=TraceListResponse)
async def list_traces(
    request: TraceListRequest,
    current_user: User = Depends(get_current_user),
):
    """
    列出追踪记录

    使用 search_after 游标分页，避免深度分页性能问题
    """
    es = get_es_client()
    service = TraceService(es)

    # 解析时间
    start_time = None
    end_time = None
    if request.start_time:
        try:
            start_time = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format")

    if request.end_time:
        try:
            end_time = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format")

    result = await service.list_traces(
        execution_type=request.execution_type,
        execution_id=request.execution_id,
        status=request.status,
        start_time=start_time,
        end_time=end_time,
        user_id=request.user_id,
        search_after=request.search_after,
        size=request.size,
    )

    return TraceListResponse(
        traces=[
            TraceListItemResponse(
                trace_id=t["trace_id"],
                execution_type=t["execution_type"],
                execution_id=t["execution_id"],
                total_spans=t.get("total_spans", 0),
                total_duration_ms=t.get("total_duration_ms", 0),
                final_status=t.get("final_status", "unknown"),
                started_at=t["started_at"],
                completed_at=t.get("completed_at"),
            )
            for t in result["traces"]
        ],
        next_search_after=result["next_search_after"],
        has_more=result["has_more"],
    )


@router.get("/{trace_id}/stats", response_model=TraceStatsResponse)
async def get_trace_stats(
    trace_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取追踪统计信息"""
    es = get_es_client()
    service = TraceService(es)

    stats = await service.get_trace_stats(trace_id)
    if stats["span_count"] == 0:
        raise HTTPException(status_code=404, detail="Trace not found")

    return TraceStatsResponse(**stats)


@router.get("/{trace_id}/duration-breakdown", response_model=List[TraceDurationBreakdownResponse])
async def get_trace_duration_breakdown(
    trace_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取追踪各阶段耗时分析"""
    es = get_es_client()
    service = TraceService(es)

    breakdown = await service.get_trace_duration_breakdown(trace_id)
    return [TraceDurationBreakdownResponse(**item) for item in breakdown]


@router.delete("/cleanup")
async def cleanup_old_traces(
    days: int = Query(90, ge=1, le=365, description="保留天数"),
    current_user: User = Depends(get_current_user),
):
    """
    清理旧的追踪数据

    注意：只有管理员可以执行此操作
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")

    es = get_es_client()
    service = TraceService(es)
    await service.cleanup_old_traces(days=days)

    return {"message": f"Cleaned up traces older than {days} days"}
