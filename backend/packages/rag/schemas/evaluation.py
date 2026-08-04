"""
Evaluation schemas - 评估请求/响应模型
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class GoldenSampleCreate(BaseModel):
    """创建 Golden Sample"""
    kb_id: str = Field(..., description="知识库 ID")
    question: str = Field(..., description="问题")
    expected_answer: str = Field(..., description="期望答案")
    expected_context_ids: Optional[List[str]] = Field(None, description="期望的上下文 ID 列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    difficulty: Optional[str] = Field(None, description="难度", pattern="^(easy|medium|hard)$")
    category: Optional[str] = Field(None, description="分类")


class GoldenSampleResponse(BaseModel):
    """Golden Sample 响应"""
    id: str
    kb_id: str
    question: str
    expected_answer: str
    expected_context_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class EvaluationRunCreate(BaseModel):
    """创建评估运行"""
    kb_id: str = Field(..., description="知识库 ID")
    name: str = Field(..., description="运行名称")
    evaluation_type: str = Field(..., description="评估类型")
    metrics: List[str] = Field(default_factory=list, description="评估指标列表")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")


class EvaluationRunResponse(BaseModel):
    """评估运行响应"""
    id: str
    kb_id: str
    name: str
    evaluation_type: str
    metrics: List[str]
    config: Optional[Dict[str, Any]] = None
    status: str
    results: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EvaluationResult(BaseModel):
    """评估结果"""
    run_id: str
    total_samples: int
    evaluated: int
    avg_scores: Dict[str, float]
    overall_score: float
    details: List[Dict[str, Any]]
