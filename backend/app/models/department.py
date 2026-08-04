"""
Department and User-Department models for organizational structure
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Table, Column, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base


class Department(Base):
    """部门模型 - 支持多级部门架构"""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 部门名称
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)  # 部门编码

    # 层级关系
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)  # 部门层级
    tree_path: Mapped[str] = mapped_column(String(500), default="/")  # 层级路径如：/1/3/5/

    # 部门类型
    dept_type: Mapped[str] = mapped_column(String(20), default="department")
    # company: 公司，department: 部门，team: 团队，project_group: 项目组

    # 负责人
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 排序

    # 描述
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    parent = relationship("Department", remote_side=[id], backref="children")
    leader = relationship("User", backref="led_departments", foreign_keys=[leader_id])
    dept_members = relationship("UserDepartment", back_populates="department", cascade="all, delete-orphan")
    primary_members = relationship("User", foreign_keys="User.primary_dept_id", back_populates="primary_department")

    def get_full_path(self) -> str:
        """获取完整路径名称"""
        parts = [self.name]
        current = self.parent
        while current:
            parts.append(current.name)
            current = current.parent
        return " / ".join(reversed(parts))


class UserDepartment(Base):
    """用户与部门的多对多关联 - 支持用户在多个部门中担任不同角色"""
    __tablename__ = "user_departments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)

    # 在部门中的角色
    dept_role: Mapped[str] = mapped_column(String(50), default="member")
    # owner, admin, member, viewer

    # 是否为主部门
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    # 加入时间
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="dept_memberships")
    department = relationship("Department", back_populates="dept_members")

    __table_args__ = (
        UniqueConstraint('user_id', 'department_id', name='uq_user_dept'),
    )
