"""
Menu model for dynamic menu configuration
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text, Table, Column, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from packages.core.base_model import Base


# Role-Menu association table
role_menus = Table(
    "role_menus",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("menu_id", Integer, ForeignKey("menus.id", ondelete="CASCADE"), primary_key=True),
)


class Menu(Base):
    """系统菜单配置 - 支持多级菜单和权限控制"""
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 菜单名称
    name_i18n: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 国际化 key

    # 菜单类型
    menu_type: Mapped[str] = mapped_column(String(20), default="menu")
    # menu: 一级菜单，sub_menu: 子菜单，button: 按钮权限

    # 路由信息
    path: Mapped[str] = mapped_column(String(255), nullable=False)  # 前端路由
    component: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 组件路径
    redirect: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 重定向路径

    # 图标和展示
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 图标
    order: Mapped[int] = mapped_column(Integer, default=0)  # 排序

    # 层级关系
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    tree_path: Mapped[str] = mapped_column(String(500), default="/")  # 层级路径如：/1/3/5/

    # 权限控制
    permission: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 所需权限
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否可见
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否隐藏（路由存在但菜单不显示）

    # 外部链接
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否外链
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 外链地址

    # 缓存
    keep_alive: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否缓存

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    parent = relationship("Menu", remote_side=[id], backref="children")
    roles = relationship("Role", secondary="role_menus", back_populates="menus")

    def get_full_path(self) -> str:
        """获取完整路径名称"""
        parts = [self.name]
        current = self.parent
        while current:
            parts.append(current.name)
            current = current.parent
        return " / ".join(reversed(parts))
