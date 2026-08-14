"""
Conversation schemas - 对话历史请求/响应模型
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """创建对话"""
    title: Optional[str] = Field(None, description="对话标题")
    kb_ids: Optional[List[str]] = Field(None, description="关联的知识库 ID 列表")


class ConversationUpdate(BaseModel):
    """更新对话"""
    title: Optional[str] = Field(None, description="对话标题")
    is_archived: Optional[bool] = Field(None, description="是否归档")


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    conversation_id: str
    role: str
    content: str
    sources: Optional[List[dict]] = None
    token_count: Optional[int] = None
    latency_ms: Optional[int] = None
    model_used: Optional[str] = None
    message_index: int
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """对话响应"""
    id: str
    user_id: Optional[int]
    title: str
    kb_ids: Optional[List[str]] = None
    is_active: bool
    is_archived: bool
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    items: List[ConversationResponse]
    total: int


class ConversationDetailResponse(BaseModel):
    """对话详情响应"""
    conversation: ConversationResponse
    messages: List[MessageResponse]


class ConversationWithMessagesResponse(BaseModel):
    """带消息的对话响应"""
    id: str
    title: str
    kb_ids: Optional[List[str]] = None
    message_count: int
    last_message_at: Optional[datetime]
    messages: List[MessageResponse]
