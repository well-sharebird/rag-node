"""
Evaluation models - 评估数据模型
"""
from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class GoldenSample(Base, TimestampMixin):
    __tablename__ = "golden_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)

    # 问题与期望答案
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)

    # 期望的上下文（chunk IDs）
    expected_context_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # 元数据
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # easy, medium, hard
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class EvaluationRun(Base, TimestampMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)

    # 运行信息
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # golden_dataset, manual, production

    # 评估指标
    metrics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of metric names

    # 配置
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, completed, failed
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 结果
    results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON results
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 统计
    total_samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Feedback(Base, TimestampMixin):
    __tablename__ = "evaluation_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # 关联
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("evaluation_runs.id"), nullable=True)
    sample_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("golden_samples.id"), nullable=True)

    # 反馈内容
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 元数据
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
