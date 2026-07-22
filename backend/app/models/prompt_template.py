"""提示词模板管理模块 - SQLAlchemy 模型

提示词工程模块：对提示词进行工业化管理
- 版本控制：每次修改生成新版本（不可变）
- 标签管理：stable/beta/dev/canary 指针
- 效果评估：LLM-as-Judge 离线评测
- 灰度发布：基于用户 ID 哈希分流
"""

from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class PromptTemplate(Base, TimestampMixin):
    """提示词模板主表"""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="system"
    )  # system | user | instruction
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active | archived

    # 关系
    versions: Mapped[list["PromptVersion"]] = relationship(
        "PromptVersion", back_populates="template", cascade="all, delete-orphan"
    )
    tags: Mapped[list["PromptTag"]] = relationship(
        "PromptTag", back_populates="template", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list["PromptTestCase"]] = relationship(
        "PromptTestCase", back_populates="template", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PromptTemplate(name='{self.name}', status='{self.status}')>"


class PromptVersion(Base, TimestampMixin):
    """提示词版本表 - 核心表（不可变）"""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )

    # 语义化版本
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    semver_major: Mapped[int] = mapped_column(Integer, default=0)
    semver_minor: Mapped[int] = mapped_column(Integer, default=0)
    semver_patch: Mapped[int] = mapped_column(Integer, default=0)
    semver_prerelease: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 核心内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{name, type, required, default}]
    system_role: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 元数据
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft | released | archived

    # 评测
    latest_eval_score: Mapped[float | None] = mapped_column(nullable=True)
    eval_dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 关系
    template: Mapped["PromptTemplate"] = relationship(
        "PromptTemplate", back_populates="versions"
    )
    eval_runs: Mapped[list["PromptEvalRun"]] = relationship(
        "PromptEvalRun",
        primaryjoin="PromptEvalRun.version_id == PromptVersion.id",
        back_populates="version",
        foreign_keys="PromptEvalRun.version_id",
    )

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="unique_template_version"),
        Index("idx_pv_template", "template_id"),
        Index("idx_pv_semver", "semver_major", "semver_minor", "semver_patch"),
        Index("idx_pv_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<PromptVersion(template_id={self.template_id}, version='{self.version}')>"


class PromptTag(Base, TimestampMixin):
    """提示词标签表 - 可变指针"""

    __tablename__ = "prompt_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )
    tag_name: Mapped[str] = mapped_column(String(50), nullable=False)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_versions.id", ondelete="CASCADE"), nullable=False
    )

    # 灰度配置
    meta_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # {gray_percent: 5, target_users: []}

    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 关系
    template: Mapped["PromptTemplate"] = relationship(
        "PromptTemplate", back_populates="tags"
    )
    version: Mapped["PromptVersion"] = relationship(
        "PromptVersion",
        primaryjoin="PromptTag.version_id == PromptVersion.id",
        foreign_keys=[version_id],
    )

    __table_args__ = (
        UniqueConstraint("template_id", "tag_name", name="unique_template_tag"),
        Index("idx_ptag_template", "template_id"),
        Index("idx_ptag_name", "tag_name"),
    )

    def __repr__(self) -> str:
        return f"<PromptTag(template_id={self.template_id}, tag='{self.tag_name}', version_id={self.version_id})>"


class PromptTestCase(Base, TimestampMixin):
    """提示词测试用例表"""

    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )

    # 测试内容
    input_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # 渲染变量：{"user_name": "Alice", "context": "..."}
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 元数据
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # ["边界条件", "正常场景"]
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1-5, 1 最高
    is_active: Mapped[bool] = mapped_column(Integer, default=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 关系
    template: Mapped["PromptTemplate"] = relationship(
        "PromptTemplate", back_populates="test_cases"
    )

    __table_args__ = (
        Index("idx_tc_template", "template_id"),
        Index("idx_tc_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<PromptTestCase(template_id={self.template_id}, priority={self.priority})>"


class PromptEvalRun(Base, TimestampMixin):
    """提示词评估运行记录表"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_versions.id", ondelete="CASCADE"), nullable=False
    )
    baseline_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("prompt_versions.id"), nullable=True
    )

    # 测试用例
    test_case_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False
    )  # [1, 2, 3, ...]

    # 汇总结果
    avg_score: Mapped[float | None] = mapped_column(nullable=True)
    pass_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fail_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 详细结果
    detailed_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # [{case_id, score, llm_output, reasoning}]

    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # manual | ci | pre_release
    run_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 关系
    version: Mapped["PromptVersion"] = relationship(
        "PromptVersion",
        primaryjoin="PromptEvalRun.version_id == PromptVersion.id",
        back_populates="eval_runs",
        foreign_keys=[version_id],
    )

    __table_args__ = (
        Index("idx_er_version", "version_id"),
        Index("idx_er_run_at", "run_at"),
    )

    def __repr__(self) -> str:
        return f"<PromptEvalRun(version_id={self.version_id}, avg_score={self.avg_score})>"


class PromptAuditLog(Base, TimestampMixin):
    """提示词审计日志表"""

    __tablename__ = "prompt_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # create | update | tag | rollback | eval
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # template | version | tag
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)

    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_actor", "actor"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_time", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PromptAuditLog(actor='{self.actor}', action='{self.action}')>"
