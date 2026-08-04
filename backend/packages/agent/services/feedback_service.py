"""
Feedback service - 反馈服务
"""
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.models.feedback import Feedback
from packages.agent.schemas.feedback import FeedbackCreate, FeedbackStats

logger = logging.getLogger("app.services.feedback")


async def create_feedback(db: AsyncSession, data: FeedbackCreate) -> Feedback:
    """创建反馈"""
    feedback = Feedback(
        session_id=data.session_id,
        message_id=data.message_id,
        feedback_type=data.feedback_type,
        rating=data.rating,
        reason_category=data.reason_category,
        reason_text=data.reason_text,
        comment=data.comment,
        query=data.query[:10000] if data.query else None,
        response=data.response[:50000] if data.response else None,
        referenced_docs=",".join(data.referenced_docs) if data.referenced_docs else None,
    )

    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        "Feedback created | id=%s type=%s session=%s",
        feedback.id, feedback.feedback_type, feedback.session_id
    )

    return feedback


async def get_feedback_stats(
    db: AsyncSession,
    kb_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> FeedbackStats:
    """获取反馈统计"""
    # Build conditions
    conditions = []
    if kb_id:
        conditions.append(Feedback.kb_id == kb_id)
    if start_date:
        conditions.append(Feedback.created_at >= start_date)
    if end_date:
        conditions.append(Feedback.created_at <= end_date)

    # Single query with aggregation
    from sqlalchemy import case, literal
    query = select(
        func.count(Feedback.id).label("total"),
        func.sum(
            case((Feedback.feedback_type == "thumbs_up", 1), else_=literal(0))
        ).label("thumbs_up"),
        func.sum(
            case((Feedback.feedback_type == "thumbs_down", 1), else_=literal(0))
        ).label("thumbs_down"),
        func.avg(Feedback.rating).label("avg_rating"),
    )
    for cond in conditions:
        query = query.where(cond)

    result = await db.execute(query)
    row = result.one()

    total = row.total or 0
    thumbs_up = row.thumbs_up or 0
    thumbs_down = row.thumbs_down or 0
    avg_rating = row.avg_rating

    # Reason breakdown
    reason_query = (
        select(Feedback.reason_category, func.count(Feedback.id))
        .where(Feedback.reason_category.isnot(None))
    )
    for cond in conditions:
        reason_query = reason_query.where(cond)
    reason_query = reason_query.group_by(Feedback.reason_category)

    reason_result = await db.execute(reason_query)
    reason_breakdown = {row[0]: row[1] for row in reason_result.all()}

    return FeedbackStats(
        total_feedback=total,
        thumbs_up=thumbs_up,
        thumbs_down=thumbs_down,
        positive_rate=thumbs_up / total if total > 0 else 0.0,
        average_rating=avg_rating,
        reason_breakdown=reason_breakdown,
    )


async def list_feedback(
    db: AsyncSession,
    kb_id: Optional[str] = None,
    feedback_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Feedback]:
    """获取反馈列表"""
    query = select(Feedback).order_by(Feedback.created_at.desc())

    if kb_id:
        query = query.where(Feedback.kb_id == kb_id)
    if feedback_type:
        query = query.where(Feedback.feedback_type == feedback_type)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


async def mark_feedback_processed(
    db: AsyncSession,
    feedback_id: str,
    processed_by: Optional[str] = None,
) -> bool:
    """标记反馈已处理"""
    await db.execute(
        update(Feedback)
        .where(Feedback.id == feedback_id)
        .values(
            is_processed=True,
            processed_at=datetime.utcnow(),
            processed_by=processed_by,
        )
    )
    await db.commit()
    return True


async def delete_feedback(db: AsyncSession, feedback_id: str) -> bool:
    """删除反馈"""
    await db.execute(delete(Feedback).where(Feedback.id == feedback_id))
    await db.commit()
    return True


async def update_feedback_helpfulness(
    db: AsyncSession,
    feedback_id: str,
    score: float,
) -> bool:
    """更新反馈有用性评分"""
    await db.execute(
        update(Feedback)
        .where(Feedback.id == feedback_id)
        .values(helpfulness_score=score)
    )
    await db.commit()
    return True
