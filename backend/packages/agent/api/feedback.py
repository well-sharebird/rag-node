"""
Feedback API - 问答反馈接口
"""
import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime

from packages.core.deps import DBSession
from packages.agent.schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackStats, FeedbackListResponse
from packages.agent.services import feedback_service

logger = logging.getLogger("app.api.feedback")
router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(db: DBSession, data: FeedbackCreate):
    """
    提交问答反馈

    - thumbs_up: 点赞（答案有用）
    - thumbs_down: 点踩（答案无用）

    点踩时建议填写原因分类：
    - irrelevant: 与问题无关
    - incorrect: 信息错误
    - incomplete: 信息不完整
    - outdated: 信息过时
    - harmful: 有害内容
    - other: 其他
    """
    feedback = await feedback_service.create_feedback(db, data)

    return FeedbackResponse(
        id=feedback.id,
        session_id=feedback.session_id,
        message_id=feedback.message_id,
        feedback_type=feedback.feedback_type,
        rating=feedback.rating,
        reason_category=feedback.reason_category,
        reason_text=feedback.reason_text,
        comment=feedback.comment,
        query=feedback.query,
        response=feedback.response,
        referenced_docs=feedback.referenced_docs.split(",") if feedback.referenced_docs else None,
        user_id=feedback.user_id,
        kb_id=feedback.kb_id,
        created_at=feedback.created_at,
        is_positive=feedback.is_positive,
    )


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(
    db: DBSession,
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
):
    """获取反馈统计"""
    return await feedback_service.get_feedback_stats(db, kb_id, start_date, end_date)


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    db: DBSession,
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    feedback_type: Optional[str] = Query(None, description="反馈类型", pattern="^(thumbs_up|thumbs_down)$"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取反馈列表"""
    items = await feedback_service.list_feedback(db, kb_id, feedback_type, limit, offset)

    # 获取总数
    total = len(items)  # 简化实现，实际应该用 count 查询

    return FeedbackListResponse(
        items=[
            FeedbackResponse(
                id=f.id,
                session_id=f.session_id,
                message_id=f.message_id,
                feedback_type=f.feedback_type,
                rating=f.rating,
                reason_category=f.reason_category,
                reason_text=f.reason_text,
                comment=f.comment,
                query=f.query,
                response=f.response,
                referenced_docs=f.referenced_docs.split(",") if f.referenced_docs else None,
                user_id=f.user_id,
                kb_id=f.kb_id,
                created_at=f.created_at,
                is_positive=f.is_positive,
            )
            for f in items
        ],
        total=total,
    )


@router.post("/{feedback_id}/process")
async def process_feedback(db: DBSession, feedback_id: str, processed_by: Optional[str] = None):
    """标记反馈已处理"""
    success = await feedback_service.mark_feedback_processed(db, feedback_id, processed_by)
    if not success:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "processed", "feedback_id": feedback_id}


@router.delete("/{feedback_id}")
async def delete_feedback(db: DBSession, feedback_id: str):
    """删除反馈"""
    success = await feedback_service.delete_feedback(db, feedback_id)
    if not success:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "deleted", "feedback_id": feedback_id}
