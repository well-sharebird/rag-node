"""
Menu Service - 菜单管理服务
"""
from typing import List, Optional
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.orm import Session, selectinload

from packages.core.system.models.menu import Menu, role_menus
from packages.core.system.models.user import User
from packages.core.system.schemas.menu import MenuCreate, MenuUpdate, MenuSyncItem


class MenuService:
    """菜单服务类"""

    def __init__(self, db: Session):
        self.db = db

    def get_menu_tree(self, parent_id: Optional[int] = None) -> List[dict]:
        """
        获取菜单树
        :param parent_id: 父菜单 ID，None 表示获取根菜单
        :return: 菜单树形结构
        """
        # 加载所有菜单，然后在内存中构建树形结构
        result = self.db.execute(
            select(Menu)
            .order_by(Menu.order, Menu.name)
        )
        all_menus = result.scalars().all()

        # 构建菜单字典（先不包含 children）
        menu_dict = {}
        for m in all_menus:
            menu_data = self._menu_to_dict(m)
            menu_data["children"] = []  # 初始化为空数组
            menu_dict[m.id] = menu_data

        # 找出根菜单（parent_id 为 None）
        root_menus = []
        for menu_id, menu_data in menu_dict.items():
            if menu_data["parent_id"] is None:
                root_menus.append(menu_data)
            else:
                # 将子菜单添加到父菜单的 children 中
                parent = menu_dict.get(menu_data["parent_id"])
                if parent:
                    parent["children"].append(menu_data)

        # 如果指定了 parent_id，只返回该菜单及其子菜单
        if parent_id is not None:
            parent_menu = menu_dict.get(parent_id)
            if parent_menu:
                return [parent_menu]
            return []

        return root_menus

    def get_all_menus(self) -> List[Menu]:
        """获取所有菜单"""
        result = self.db.execute(
            select(Menu)
            .options(selectinload(Menu.children))
            .order_by(Menu.order, Menu.name)
        )
        return result.scalars().all()

    def get_menu(self, menu_id: int) -> Optional[Menu]:
        """
        获取菜单详情
        :param menu_id: 菜单 ID
        :return: 菜单对象
        """
        result = self.db.execute(
            select(Menu)
            .where(Menu.id == menu_id)
            .options(selectinload(Menu.children))
        )
        return result.scalar_one_or_none()

    def create_menu(self, data: MenuCreate) -> Menu:
        """
        创建菜单
        :param data: 菜单创建数据
        :return: 创建的菜单
        """
        menu = Menu(**data.model_dump(exclude={'parent_id'}))
        menu.parent_id = data.parent_id

        # 计算层级和路径
        if data.parent_id:
            parent = self.get_menu(data.parent_id)
            if parent:
                menu.level = parent.level + 1
                menu.tree_path = f"{parent.tree_path}{menu.id}/"
            else:
                menu.level = 1
                menu.tree_path = f"/{menu.id}/"
        else:
            menu.level = 1
            menu.tree_path = f"/{menu.id}/"

        self.db.add(menu)
        self.db.commit()
        self.db.refresh(menu)
        return menu

    def update_menu(self, menu_id: int, data: MenuUpdate) -> Optional[Menu]:
        """
        更新菜单
        :param menu_id: 菜单 ID
        :param data: 菜单更新数据
        :return: 更新后的菜单
        """
        menu = self.get_menu(menu_id)
        if not menu:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(menu, field, value)

        # 如果修改了父菜单，需要更新层级和路径
        if 'parent_id' in update_data:
            if data.parent_id:
                parent = self.get_menu(data.parent_id)
                if parent:
                    menu.level = parent.level + 1
                    menu.tree_path = f"{parent.tree_path}{menu.id}/"
            else:
                menu.level = 1
                menu.tree_path = f"/{menu.id}/"

        self.db.commit()
        self.db.refresh(menu)
        return menu

    def delete_menu(self, menu_id: int) -> bool:
        """
        删除菜单
        :param menu_id: 菜单 ID
        :return: 是否删除成功
        """
        menu = self.get_menu(menu_id)
        if not menu:
            return False

        # 检查是否有子菜单
        if menu.children:
            raise ValueError("无法删除包含子菜单的菜单")

        self.db.delete(menu)
        self.db.commit()
        return True

    def get_user_menus(self, user_id: int) -> List[Menu]:
        """
        获取用户有权限的菜单
        :param user_id: 用户 ID
        :return: 菜单列表
        """
        # 获取用户
        user_result = self.db.execute(
            select(User)
            .options(selectinload(User.roles).selectinload("menus"))
            .where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return []

        # 超级管理员返回所有菜单（检查 is_superuser 字段或 super_admin 角色）
        if user.is_superuser or any(role.name == 'super_admin' for role in user.roles):
            return self.get_all_menus()

        # 收集用户所有角色的菜单
        menu_ids = set()
        for role in user.roles:
            for menu in role.menus:
                menu_ids.add(menu.id)

        if not menu_ids:
            return []

        result = self.db.execute(
            select(Menu)
            .where(Menu.id.in_(menu_ids))
            .where(Menu.is_active == True)
            .where(Menu.is_visible == True)
            .order_by(Menu.order, Menu.name)
        )
        return result.scalars().all()

    def get_user_menu_tree(self, user_id: int) -> List[dict]:
        """
        获取用户有权限的菜单树
        :param user_id: 用户 ID
        :return: 菜单树形结构
        """
        menus = self.get_user_menus(user_id)
        return self._build_menu_tree(menus)

    def assign_menus_to_role(self, role_id: int, menu_ids: List[int]) -> bool:
        """
        为角色分配菜单
        :param role_id: 角色 ID
        :param menu_ids: 菜单 ID 列表
        :return: 是否成功
        """
        # 删除现有的菜单关联
        self.db.execute(
            sql_delete(role_menus).where(role_menus.c.role_id == role_id)
        )

        # 添加新的菜单关联
        if menu_ids:
            for menu_id in menu_ids:
                self.db.execute(role_menus.insert().values(role_id=role_id, menu_id=menu_id))

        self.db.commit()
        return True

    def sync_menus(self, sync_items: List[MenuSyncItem]) -> dict:
        """
        同步菜单（用于前端路由同步）
        :param sync_items: 菜单同步项列表
        :return: 同步结果
        """
        created = 0
        updated = 0
        deleted = 0

        # 获取现有菜单
        existing_result = self.db.execute(select(Menu))
        existing_menus = {m.path: m for m in existing_result.scalars().all()}

        sync_paths = set()

        for item in sync_items:
            sync_paths.add(item.path)

            if item.path in existing_menus:
                # 更新现有菜单
                menu = existing_menus[item.path]
                menu.name = item.name
                menu.name_i18n = item.name_i18n
                menu.menu_type = item.menu_type
                menu.component = item.component
                menu.icon = item.icon
                menu.order = item.order
                menu.permission = item.permission
                menu.is_visible = item.is_visible
                menu.is_hidden = item.is_hidden
                updated += 1
            else:
                # 创建新菜单
                menu = Menu(
                    path=item.path,
                    name=item.name,
                    name_i18n=item.name_i18n,
                    menu_type=item.menu_type,
                    component=item.component,
                    icon=item.icon,
                    order=item.order,
                    permission=item.permission,
                    is_visible=item.is_visible,
                    is_hidden=item.is_hidden,
                    is_active=True,
                )
                self.db.add(menu)
                created += 1

        self.db.commit()

        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
        }

    def _menu_to_dict(self, menu: Menu) -> dict:
        """将菜单对象转换为字典"""
        return {
            "id": menu.id,
            "name": menu.name,
            "name_i18n": menu.name_i18n,
            "menu_type": menu.menu_type,
            "path": menu.path,
            "component": menu.component,
            "redirect": menu.redirect,
            "icon": menu.icon,
            "order": menu.order,
            "parent_id": menu.parent_id,
            "level": menu.level,
            "tree_path": menu.tree_path,
            "permission": menu.permission,
            "is_visible": menu.is_visible,
            "is_hidden": menu.is_hidden,
            "is_external": menu.is_external,
            "external_url": menu.external_url,
            "keep_alive": menu.keep_alive,
            "is_active": menu.is_active,
            "created_at": menu.created_at,
            "updated_at": menu.updated_at,
            "children": [self._menu_to_dict(child) for child in menu.children]
        }

    def _build_menu_tree(self, menus: List[Menu]) -> List[dict]:
        """
        从菜单列表构建树形结构
        :param menus: 菜单列表
        :return: 菜单树
        """
        menu_dict = {m.id: self._menu_to_dict(m) for m in menus}
        root_menus = []

        for menu_id, menu_data in menu_dict.items():
            if menu_data["parent_id"] is None:
                root_menus.append(menu_data)
            else:
                # 查找父菜单并添加到 children
                parent = menu_dict.get(menu_data["parent_id"])
                if parent:
                    if "children" not in parent:
                        parent["children"] = []
                    parent["children"].append(menu_data)

        return root_menus
