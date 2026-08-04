# 后台权限管理系统设计文档

> 文档版本：1.0  
> 创建时间：2026-07-30  
> 最后更新：2026-07-30

---

## 一、现有基础分析

### ✅ 已有模型

| 模型 | 位置 | 状态 |
|------|------|------|
| `User` | `backend/app/models/user.py` | ✅ 完整 |
| `Role` | `backend/app/models/user.py` | ✅ 完整 |
| `Permission` | `backend/app/models/user.py` | ✅ 完整 |
| `APIKey` | `backend/app/models/user.py` | ✅ 完整 |
| `AuditLog` | `backend/app/models/user.py` | ✅ 完整 |

### ✅ 已有功能

- JWT Token 认证 (`auth.py`)
- 角色权限检查 (`require_role()`, `require_permission()`)
- API Key 认证
- 审计日志记录

### ❌ 缺失内容

- **部门管理** - 多级部门架构
- **菜单管理** - 动态菜单配置、菜单权限
- **用户 - 部门关联** - 用户在部门中的角色
- **后台管理 API** - 完整的 CRUD 接口

---

## 二、数据模型设计

### 2.1 部门模型 (Department)

```python
class Department(Base):
    """部门模型 - 支持多级部门架构"""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 部门名称
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 部门编码
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)  # 父部门
    level: Mapped[int] = mapped_column(Integer, default=1)  # 部门层级
    path: Mapped[str] = mapped_column(String(500))  # 层级路径如：/1/3/5/
    
    # 部门类型
    dept_type: Mapped[str] = mapped_column(String(20), default="department")  
    # company: 公司，department: 部门，team: 团队，project_group: 项目组
    
    # 负责人
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    
    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 排序
    
    # 描述
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    parent = relationship("Department", remote_side=[id], backref="children")
    leader = relationship("User", backref="led_departments")
    users = relationship("UserDepartment", back_populates="department", cascade="all, delete-orphan")
```

### 2.2 用户 - 部门关联 (UserDepartment)

```python
class UserDepartment(Base):
    """用户与部门的多对多关联 - 支持用户在多个部门中担任不同角色"""
    __tablename__ = "user_departments"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    user = relationship("User", backref="dept_memberships")
    department = relationship("Department", back_populates="users")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'department_id', name='uq_user_dept'),
    )
```

### 2.3 菜单模型 (Menu)

```python
class Menu(Base):
    """系统菜单配置 - 支持多级菜单和权限控制"""
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("menus.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(String(500))  # 层级路径
    
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
    
    # 关系
    parent = relationship("Menu", remote_side=[id], backref="children")
    roles = relationship("Role", secondary="role_menus", back_populates="menus")
```

### 2.4 角色 - 菜单关联 (RoleMenu)

```python
role_menus = Table(
    "role_menus",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("menu_id", Integer, ForeignKey("menus.id", ondelete="CASCADE"), primary_key=True),
)
```

### 2.5 扩展现有模型

```python
# 扩展 User 模型
class User(Base):
    # ... 现有字段 ...
    
    # 新增：主部门 ID
    primary_dept_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    
    # 关系
    primary_department = relationship("Department", foreign_keys=[primary_dept_id])

# 扩展 Role 模型
class Role(Base):
    # ... 现有字段 ...
    
    # 新增：菜单权限
    menus = relationship("Menu", secondary=role_menus, back_populates="roles")
```

---

## 三、API 接口设计

### 3.1 部门管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/admin/departments` | 获取部门树 | `dept:read` |
| GET | `/api/v1/admin/departments/{id}` | 获取部门详情 | `dept:read` |
| POST | `/api/v1/admin/departments` | 创建部门 | `dept:create` |
| PUT | `/api/v1/admin/departments/{id}` | 更新部门 | `dept:update` |
| DELETE | `/api/v1/admin/departments/{id}` | 删除部门 | `dept:delete` |
| GET | `/api/v1/admin/departments/{id}/users` | 获取部门下用户 | `dept:read` |
| POST | `/api/v1/admin/departments/{id}/users` | 添加用户到部门 | `dept:manage` |
| DELETE | `/api/v1/admin/departments/{id}/users/{user_id}` | 从部门移除用户 | `dept:manage` |

### 3.2 菜单管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/admin/menus` | 获取菜单树 | `menu:read` |
| GET | `/api/v1/admin/menus/{id}` | 获取菜单详情 | `menu:read` |
| POST | `/api/v1/admin/menus` | 创建菜单 | `menu:create` |
| PUT | `/api/v1/admin/menus/{id}` | 更新菜单 | `menu:update` |
| DELETE | `/api/v1/admin/menus/{id}` | 删除菜单 | `menu:delete` |
| GET | `/api/v1/admin/menus/tree` | 获取完整菜单树 | `menu:read` |
| POST | `/api/v1/admin/menus/sync` | 同步菜单（前端路由） | `menu:manage` |

### 3.3 用户管理 API（扩展）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/admin/users` | 用户列表 | `user:read` |
| GET | `/api/v1/admin/users/{id}` | 用户详情 | `user:read` |
| POST | `/api/v1/admin/users` | 创建用户 | `user:create` |
| PUT | `/api/v1/admin/users/{id}` | 更新用户 | `user:update` |
| DELETE | `/api/v1/admin/users/{id}` | 删除用户 | `user:delete` |
| POST | `/api/v1/admin/users/{id}/roles` | 分配角色 | `user:manage` |
| DELETE | `/api/v1/admin/users/{id}/roles/{role_id}` | 移除角色 | `user:manage` |
| PUT | `/api/v1/admin/users/{id}/departments` | 设置用户部门 | `user:manage` |
| GET | `/api/v1/admin/users/{id}/permissions` | 获取用户权限 | `user:read` |

### 3.4 角色管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/admin/roles` | 角色列表 | `role:read` |
| GET | `/api/v1/admin/roles/{id}` | 角色详情 | `role:read` |
| POST | `/api/v1/admin/roles` | 创建角色 | `role:create` |
| PUT | `/api/v1/admin/roles/{id}` | 更新角色 | `role:update` |
| DELETE | `/api/v1/admin/roles/{id}` | 删除角色 | `role:delete` |
| PUT | `/api/v1/admin/roles/{id}/permissions` | 设置角色权限 | `role:manage` |
| PUT | `/api/v1/admin/roles/{id}/menus` | 设置角色菜单 | `role:manage` |

### 3.5 当前用户 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/auth/me` | 获取当前用户信息 |
| GET | `/api/v1/auth/me/menus` | 获取当前用户菜单 |
| GET | `/api/v1/auth/me/permissions` | 获取当前用户权限 |
| GET | `/api/v1/auth/me/departments` | 获取当前用户部门 |
| PUT | `/api/v1/auth/me/password` | 修改密码 |

---

## 四、权限点设计

### 4.1 资源权限

```python
# 部门管理
"dept:read"      - 查看部门
"dept:create"    - 创建部门
"dept:update"    - 更新部门
"dept:delete"    - 删除部门
"dept:manage"    - 管理部门成员

# 菜单管理
"menu:read"     - 查看菜单
"menu:create"   - 创建菜单
"menu:update"   - 更新菜单
"menu:delete"   - 删除菜单
"menu:manage"   - 管理菜单（同步等）

# 用户管理
"user:read"     - 查看用户
"user:create"   - 创建用户
"user:update"   - 更新用户
"user:delete"   - 删除用户
"user:manage"   - 管理用户（角色分配等）

# 角色管理
"role:read"     - 查看角色
"role:create"   - 创建角色
"role:update"   - 更新角色
"role:delete"   - 删除角色
"role:manage"   - 管理角色（权限分配等）
```

### 4.2 预定义角色

| 角色 | Code | 说明 | 可删除 |
|------|------|------|--------|
| 超级管理员 | `super_admin` | 系统全部权限 | ❌ |
| 系统管理员 | `admin` | 后台管理权限 | ❌ |
| 部门管理员 | `dept_admin` | 本部门管理权限 | ❌ |
| 普通用户 | `user` | 基础用户权限 | ❌ |
| 访客 | `guest` | 只读权限 | ✅ |

---

## 五、Service 层设计

### 5.1 部门服务 (DepartmentService)

```python
class DepartmentService:
    async def get_dept_tree(self, parent_id: Optional[int] = None) -> list[dict]
    async def get_department(self, dept_id: int) -> Department | None
    async def create_department(self, data: DeptCreate) -> Department
    async def update_department(self, dept_id: int, data: DeptUpdate) -> Department
    async def delete_department(self, dept_id: int) -> bool
    async def get_dept_users(self, dept_id: int) -> list[User]
    async def add_user_to_dept(self, dept_id: int, user_id: int, role: str) -> UserDepartment
    async def remove_user_from_dept(self, dept_id: int, user_id: int) -> bool
    async def get_user_departments(self, user_id: int) -> list[Department]
```

### 5.2 菜单服务 (MenuService)

```python
class MenuService:
    async def get_menu_tree(self, parent_id: Optional[int] = None) -> list[dict]
    async def get_user_menus(self, user_id: int) -> list[Menu]
    async def get_menu(self, menu_id: int) -> Menu | None
    async def create_menu(self, data: MenuCreate) -> Menu
    async def update_menu(self, menu_id: int, data: MenuUpdate) -> Menu
    async def delete_menu(self, menu_id: int) -> bool
    async def sync_menus(self, menus: list[MenuSyncItem]) -> dict
```

### 5.3 用户服务 (UserService) - 扩展

```python
class UserService:
    # ... 现有方法 ...
    async def get_user_permissions(self, user_id: int) -> list[str]
    async def get_user_menu_tree(self, user_id: int) -> list[dict]
    async def assign_roles(self, user_id: int, role_ids: list[int]) -> User
    async def set_user_departments(self, user_id: int, dept_ids: list[int], primary_dept_id: Optional[int]) -> User
```

---

## 六、前端组件设计

### 6.1 页面结构

```
src/pages/
├── admin/
│   ├── UserManagement.tsx       # 用户管理
│   ├── RoleManagement.tsx       # 角色管理
│   ├── DepartmentManagement.tsx  # 部门管理
│   └── MenuManagement.tsx       # 菜单管理
```

### 6.2 核心组件

```
src/components/admin/
├── DepartmentTree.tsx           # 部门树形选择器
├── MenuTree.tsx                 # 菜单树形编辑器
├── RoleSelector.tsx             # 角色选择器
├── PermissionMatrix.tsx         # 权限矩阵配置
└── UserDeptSelector.tsx         # 用户 - 部门关联选择器
```

### 6.3 菜单渲染

```tsx
// 根据用户权限动态渲染菜单
<Menu items={userMenus} />

// 按钮级权限控制
<Permission required="user:create">
  <Button>创建用户</Button>
</Permission>
```

---

## 七、实施计划

### 阶段一：数据模型（1 周）

| 任务 | 预计工时 | 依赖 |
|------|----------|------|
| 创建 Department 模型 | 0.5 天 | - |
| 创建 UserDepartment 模型 | 0.5 天 | Department |
| 创建 Menu 模型 | 0.5 天 | - |
| 创建 RoleMenu 关联表 | 0.5 天 | Menu, Role |
| 扩展现有 User/Role 模型 | 0.5 天 | - |
| Alembic 迁移脚本 | 0.5 天 | 以上模型 |

### 阶段二：后端 API（2 周）

| 任务 | 预计工时 | 依赖 |
|------|----------|------|
| 部门管理 API | 2 天 | 阶段一 |
| 菜单管理 API | 2 天 | 阶段一 |
| 用户管理 API 扩展 | 2 天 | 阶段一 |
| 角色管理 API 扩展 | 2 天 | 阶段一 |
| 当前用户 API | 1 天 | 以上 |

### 阶段三：前端实现（2 周）

| 任务 | 预计工时 | 依赖 |
|------|----------|------|
| 部门管理页面 | 2 天 | 后端 API |
| 菜单管理页面 | 2 天 | 后端 API |
| 用户管理页面扩展 | 2 天 | 后端 API |
| 角色管理页面扩展 | 2 天 | 后端 API |
| 动态菜单组件 | 2 天 | 后端 API |

### 阶段四：集成测试（1 周）

| 任务 | 预计工时 |
|------|----------|
| 单元测试 | 2 天 |
| 集成测试 | 2 天 |
| 权限测试 | 1 天 |

---

## 八、数据初始化

### 8.1 默认部门

```python
default_dept = Department(
    name="默认部门",
    code="default",
    dept_type="company",
    level=1,
    path="/1/",
)
```

### 8.2 默认菜单

```python
admin_menu = Menu(
    name="系统管理",
    name_i18n="menu.admin",
    menu_type="menu",
    path="/admin",
    icon="Settings",
    order=100,
)

user_menu = Menu(
    name="用户管理",
    name_i18n="menu.users",
    menu_type="sub_menu",
    parent_id=admin_menu.id,
    path="/admin/users",
    component="admin/UserManagement",
    permission="user:read",
)
```

---

## 九、相关文件

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/models/user.py` | 现有用户模型 |
| `backend/app/models/department.py` | 新建 - 部门模型 |
| `backend/app/models/menu.py` | 新建 - 菜单模型 |
| `backend/app/api/v1/admin.py` | 新建 - 管理 API |
| `backend/app/services/department_service.py` | 新建 - 部门服务 |
| `backend/app/services/menu_service.py` | 新建 - 菜单服务 |
| `backend/app/services/user_service.py` | 扩展现有 |

### 前端

| 文件 | 说明 |
|------|------|
| `src/pages/admin/UserManagement.tsx` | 新建 |
| `src/pages/admin/RoleManagement.tsx` | 新建 |
| `src/pages/admin/OrganizationManagement.tsx` | 新建 |
| `src/pages/admin/MenuManagement.tsx` | 新建 |
| `src/components/admin/*` | 新建公共组件 |

---

## 十、变更记录

| 日期 | 变更内容 | 作者 |
|------|----------|------|
| 2026-07-30 | 初始版本 | - |
