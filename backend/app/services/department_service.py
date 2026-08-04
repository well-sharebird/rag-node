"""
Department Service - 部门管理服务
"""
from typing import List, Optional
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.orm import Session, selectinload

from app.models.department import Department, UserDepartment
from app.models.user import User
from app.schemas.department import DepartmentCreate, DepartmentUpdate, UserDepartmentCreate


class DepartmentService:
    """部门服务类"""

    def __init__(self, db: Session):
        self.db = db

    def get_dept_tree(self, parent_id: Optional[int] = None) -> List[dict]:
        """
        获取部门树
        :param parent_id: 父部门 ID，None 表示获取根部门
        :return: 部门树形结构
        """
        if parent_id is None:
            result = self.db.execute(
                select(Department)
                .where(Department.parent_id.is_(None))
                .options(selectinload(Department.children))
                .order_by(Department.sort_order, Department.name)
            )
        else:
            result = self.db.execute(
                select(Department)
                .where(Department.parent_id == parent_id)
                .options(selectinload(Department.children))
                .order_by(Department.sort_order, Department.name)
            )

        departments = result.scalars().all()
        return [self._dept_to_dict(dept) for dept in departments]

    def get_all_depts(self) -> List[Department]:
        """获取所有部门"""
        result = self.db.execute(
            select(Department)
            .options(selectinload(Department.children))
            .order_by(Department.sort_order, Department.name)
        )
        return result.scalars().all()

    def get_department(self, dept_id: int) -> Optional[Department]:
        """
        获取部门详情
        :param dept_id: 部门 ID
        :return: 部门对象
        """
        result = self.db.execute(
            select(Department)
            .where(Department.id == dept_id)
            .options(selectinload(Department.children))
        )
        return result.scalar_one_or_none()

    def create_department(self, data: DepartmentCreate) -> Department:
        """
        创建部门
        :param data: 部门创建数据
        :return: 创建的部门
        """
        # 检查部门编码是否存在
        existing = self.db.execute(
            select(Department).where(Department.code == data.code)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"部门编码 '{data.code}' 已存在")

        # 构建部门
        dept = Department(**data.model_dump(exclude={'parent_id'}))
        dept.parent_id = data.parent_id

        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)

        # 计算层级和路径
        if data.parent_id:
            parent = self.get_department(data.parent_id)
            if parent:
                dept.level = parent.level + 1
                dept.tree_path = f"{parent.tree_path}{dept.id}/"
            else:
                dept.level = 1
                dept.tree_path = f"/{dept.id}/"
        else:
            dept.level = 1
            dept.tree_path = f"/{dept.id}/"

        self.db.commit()
        self.db.refresh(dept)
        return dept

    def update_department(self, dept_id: int, data: DepartmentUpdate) -> Optional[Department]:
        """
        更新部门
        :param dept_id: 部门 ID
        :param data: 部门更新数据
        :return: 更新后的部门
        """
        dept = self.get_department(dept_id)
        if not dept:
            return None

        # 检查部门编码是否存在（排除自己）
        if data.code:
            existing = self.db.execute(
                select(Department).where(
                    (Department.code == data.code) & (Department.id != dept_id)
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"部门编码 '{data.code}' 已存在")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(dept, field, value)

        # 如果修改了父部门，需要更新层级和路径
        if 'parent_id' in update_data:
            if data.parent_id:
                parent = self.get_department(data.parent_id)
                if parent:
                    dept.level = parent.level + 1
                    dept.tree_path = f"{parent.tree_path}{dept.id}/"
            else:
                dept.level = 1
                dept.tree_path = f"/{dept.id}/"

        self.db.commit()
        self.db.refresh(dept)
        return dept

    def delete_department(self, dept_id: int) -> bool:
        """
        删除部门
        :param dept_id: 部门 ID
        :return: 是否删除成功
        """
        dept = self.get_department(dept_id)
        if not dept:
            return False

        # 检查是否有子部门
        if dept.children:
            raise ValueError("无法删除包含子部门的部门")

        self.db.delete(dept)
        self.db.commit()
        return True

    def get_dept_users(self, dept_id: int) -> List[User]:
        """
        获取部门下的用户
        :param dept_id: 部门 ID
        :return: 用户列表
        """
        result = self.db.execute(
            select(User)
            .join(UserDepartment)
            .where(UserDepartment.department_id == dept_id)
            .options(selectinload(User.roles))
        )
        return result.scalars().unique().all()

    def add_user_to_dept(
        self,
        dept_id: int,
        user_id: int,
        role: str = "member",
        is_primary: bool = False
    ) -> UserDepartment:
        """
        添加用户到部门
        :param dept_id: 部门 ID
        :param user_id: 用户 ID
        :param role: 在部门中的角色
        :param is_primary: 是否为主部门
        :return: UserDepartment 对象
        """
        # 检查部门是否存在
        dept = self.get_department(dept_id)
        if not dept:
            raise ValueError("部门不存在")

        # 检查用户是否存在
        user_result = self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")

        # 检查是否已存在关联
        existing = self.db.execute(
            select(UserDepartment).where(
                (UserDepartment.user_id == user_id) & (UserDepartment.department_id == dept_id)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("用户已在该部门中")

        # 如果设置为主部门，取消其他主部门
        if is_primary:
            self.db.execute(
                sql_delete(UserDepartment).where(
                    (UserDepartment.user_id == user_id) & (UserDepartment.is_primary == True)
                )
            )

        user_dept = UserDepartment(
            user_id=user_id,
            department_id=dept_id,
            dept_role=role,
            is_primary=is_primary
        )
        self.db.add(user_dept)
        self.db.commit()
        self.db.refresh(user_dept)
        return user_dept

    def remove_user_from_dept(self, dept_id: int, user_id: int) -> bool:
        """
        从部门移除用户
        :param dept_id: 部门 ID
        :param user_id: 用户 ID
        :return: 是否删除成功
        """
        result = self.db.execute(
            select(UserDepartment).where(
                (UserDepartment.user_id == user_id) & (UserDepartment.department_id == dept_id)
            )
        )
        user_dept = result.scalar_one_or_none()
        if not user_dept:
            return False

        self.db.delete(user_dept)
        self.db.commit()
        return True

    def get_user_departments(self, user_id: int) -> List[Department]:
        """
        获取用户所属的所有部门
        :param user_id: 用户 ID
        :return: 部门列表
        """
        result = self.db.execute(
            select(Department)
            .join(UserDepartment)
            .where(UserDepartment.user_id == user_id)
            .order_by(UserDepartment.is_primary.desc(), Department.sort_order)
        )
        return result.scalars().all()

    def _dept_to_dict(self, dept: Department) -> dict:
        """将部门对象转换为字典"""
        return {
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "parent_id": dept.parent_id,
            "level": dept.level,
            "tree_path": dept.tree_path,
            "dept_type": dept.dept_type,
            "leader_id": dept.leader_id,
            "leader_name": dept.leader.full_name if hasattr(dept.leader, 'full_name') else None,
            "is_active": dept.is_active,
            "sort_order": dept.sort_order,
            "description": dept.description,
            "created_at": dept.created_at,
            "updated_at": dept.updated_at,
            "children": [self._dept_to_dict(child) for child in dept.children]
        }
