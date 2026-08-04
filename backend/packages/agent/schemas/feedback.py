"""
Feedback schemas - 反馈请求/响应模型
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """创建反馈"""
    session_id: str = Field(..., description="会话 ID")
    message_id: Optional[str] = Field(None, description="消息 ID")
    feedback_type: str = Field(..., description="反馈类型", pattern="^(thumbs_up|thumbs_down)$")
    rating: Optional[int] = Field(None, description="评分 1-5", ge=1, le=5)
    reason_category: Optional[str] = Field(None, description="原因分类")
    reason_text: Optional[str] = Field(None, description="原因说明")
    comment: Optional[str] = Field(None, description="额外评论")
    query: Optional[str] = Field(None, description="用户问题快照")
    response: Optional[str] = Field(None, description="回答快照")
    referenced_docs: Optional[List[str]] = Field(None, description="引用的文档 ID 列表")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    id: str
    session_id: str
    message_id: Optional[str]
    feedback_type: str
    rating: Optional[int]
    reason_category: Optional[str]
    reason_text: Optional[str]
    comment: Optional[str]
    query: Optional[str]
    response: Optional[str]
    referenced_docs: Optional[List[str]]
    user_id: Optional[str]
    kb_id: Optional[str]
    created_at: datetime
    is_positive: bool

    class Config:
        from_attributes = True


class FeedbackStats(BaseModel):
    """反馈统计"""
    total_feedback: int = 0
    thumbs_up: int = 0
    thumbs_down: int = 0
    positive_rate: float = 0.0  # 0-1
    average_rating: Optional[float] = None
    reason_breakdown: dict = Field(default_factory=dict)  # {reason_category: count}


class FeedbackListResponse(BaseModel):
    """反馈列表响应"""
    items: List[FeedbackResponse]
    total: int
    stats: Optional[FeedbackStats] = None
