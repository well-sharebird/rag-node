"""
Initialize default roles, permissions, admin user, departments, and menus
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from packages.core.system.models.user import User, Role, Permission
from packages.core.system.models.department import Department
from packages.core.system.models.menu import Menu
from packages.core.security import hash_password

logger = logging.getLogger(__name__)


# RBAC 权限定义
RBAC_PERMISSIONS = [
    # 部门管理
    ("dept:read", "department", "read", "查看部门"),
    ("dept:create", "department", "create", "创建部门"),
    ("dept:update", "department", "update", "更新部门"),
    ("dept:delete", "department", "delete", "删除部门"),
    ("dept:manage", "department", "manage", "管理部门成员"),
    # 菜单管理
    ("menu:read", "menu", "read", "查看菜单"),
    ("menu:create", "menu", "create", "创建菜单"),
    ("menu:update", "menu", "update", "更新菜单"),
    ("menu:delete", "menu", "delete", "删除菜单"),
    ("menu:manage", "menu", "manage", "管理菜单"),
    # 用户管理
    ("user:read", "user", "read", "查看用户"),
    ("user:create", "user", "create", "创建用户"),
    ("user:update", "user", "update", "更新用户"),
    ("user:delete", "user", "delete", "删除用户"),
    ("user:manage", "user", "manage", "管理用户"),
    # 角色管理
    ("role:read", "role", "read", "查看角色"),
    ("role:create", "role", "create", "创建角色"),
    ("role:update", "role", "update", "更新角色"),
    ("role:delete", "role", "delete", "删除角色"),
    ("role:manage", "role", "manage", "管理角色"),
]

# 原有权限定义（保持兼容）
LEGACY_PERMISSIONS = [
    # Knowledge Base
    ("knowledge_base", "create"),
    ("knowledge_base", "read"),
    ("knowledge_base", "update"),
    ("knowledge_base", "delete"),
    # Document
    ("document", "create"),
    ("document", "read"),
    ("document", "update"),
    ("document", "delete"),
    # Retrieval
    ("retrieval", "search"),
    ("retrieval", "chat"),
    # Settings
    ("settings", "read"),
    ("settings", "update"),
    # Admin
    ("admin", "manage_users"),
    ("admin", "view_audit_logs"),
]

DEFAULT_PERMISSIONS = RBAC_PERMISSIONS + LEGACY_PERMISSIONS

DEFAULT_ROLES = [
    {
        "name": "Admin",
        "description": "平台全量控制：用户管理、角色分配、系统配置、审计日志查看、告警管理",
        "is_system": True,
        "permissions": [p for p in DEFAULT_PERMISSIONS],
    },
    {
        "name": "Editor",
        "description": "知识库内容运营：上传文档、管理连接器、审查分块质量、运行评估测试",
        "is_system": True,
        "permissions": [
            ("knowledge_base", "create"),
            ("knowledge_base", "read"),
            ("knowledge_base", "update"),
            ("document", "create"),
            ("document", "read"),
            ("document", "update"),
            ("document", "delete"),
            ("retrieval", "search"),
            ("retrieval", "chat"),
            ("settings", "read"),
        ],
    },
    {
        "name": "Viewer",
        "description": "纯查询权限：在授权知识库范围内提问、查看引用来源、反馈答案质量",
        "is_system": True,
        "permissions": [
            ("knowledge_base", "read"),
            ("document", "read"),
            ("retrieval", "search"),
            ("retrieval", "chat"),
            ("settings", "read"),
        ],
    },
    {
        "name": "Developer",
        "description": "程序化集成：通过 API 构建自定义应用、集成聊天机器人、管理 API Keys",
        "is_system": True,
        "permissions": [
            ("knowledge_base", "read"),
            ("document", "read"),
            ("retrieval", "search"),
            ("retrieval", "chat"),
            ("settings", "read"),
            ("api_key", "create"),
            ("api_key", "read"),
            ("api_key", "update"),
            ("api_key", "delete"),
        ],
    },
]


async def init_rbac_permissions(db: AsyncSession):
    """Initialize RBAC permissions"""
    logger.info("Initializing RBAC permissions...")

    for perm_name, resource, action, description in RBAC_PERMISSIONS:
        stmt = select(Permission).where(Permission.name == perm_name)
        result = await db.execute(stmt)
        perm = result.scalar_one_or_none()

        if not perm:
            perm = Permission(
                name=perm_name,
                description=description,
                resource=resource,
                action=action,
            )
            db.add(perm)
            logger.info(f"Created permission: {perm_name}")

    await db.commit()
    logger.info("RBAC permissions initialized")


async def init_legacy_permissions(db: AsyncSession):
    """Initialize legacy permissions"""
    logger.info("Initializing legacy permissions...")

    for resource, action in LEGACY_PERMISSIONS:
        stmt = select(Permission).where(
            Permission.name == f"{resource}.{action}"
        )
        result = await db.execute(stmt)
        perm = result.scalar_one_or_none()

        if not perm:
            perm = Permission(
                name=f"{resource}.{action}",
                description=f"Permission to {action} {resource}",
                resource=resource,
                action=action,
            )
            db.add(perm)
            logger.info(f"Created permission: {resource}.{action}")

    await db.commit()
    logger.info("Legacy permissions initialized")


async def init_rbac_roles(db: AsyncSession):
    """Initialize RBAC roles"""
    logger.info("Initializing RBAC roles...")

    # 获取所有权限
    result = await db.execute(select(Permission))
    all_permissions = result.scalars().all()
    perm_dict = {p.name: p for p in all_permissions}

    # 获取所有菜单
    result = await db.execute(select(Menu))
    all_menus = result.scalars().all()
    menu_dict = {m.id: m for m in all_menus}

    # 定义 RBAC 角色
    rbac_roles = [
        {
            "name": "super_admin",
            "description": "超级管理员 - 系统全部权限",
            "is_system": True,
            "permission_names": list(perm_dict.keys()),
            "menu_ids": list(menu_dict.keys()),
        },
        {
            "name": "admin",
            "description": "系统管理员 - 后台管理权限",
            "is_system": True,
            "permission_names": list(perm_dict.keys()),
            "menu_ids": list(menu_dict.keys()),
        },
        {
            "name": "dept_admin",
            "description": "部门管理员 - 本部门管理权限",
            "is_system": True,
            "permission_names": [p.name for p in all_permissions if "dept:" in p.name],
            "menu_ids": [m.id for m in all_menus if "department" in m.path.lower()],
        },
        {
            "name": "user",
            "description": "普通用户 - 基础用户权限",
            "is_system": True,
            "permission_names": [],
            "menu_ids": [],
        },
        {
            "name": "guest",
            "description": "访客 - 只读权限",
            "is_system": False,
            "permission_names": [p.name for p in all_permissions if ":read" in p.name],
            "menu_ids": [],
        },
    ]

    for role_data in rbac_roles:
        stmt = select(Role).where(Role.name == role_data["name"])
        result = await db.execute(stmt)
        role = result.scalar_one_or_none()

        if not role:
            role = Role(
                name=role_data["name"],
                description=role_data["description"],
                is_system=role_data["is_system"],
            )
            db.add(role)
            await db.flush()
            await db.refresh(role)  # 刷新以加载 relationship

            # 分配权限
            for perm_name in role_data["permission_names"]:
                if perm_name in perm_dict:
                    role.permissions.append(perm_dict[perm_name])

            # 分配菜单
            for menu_id in role_data["menu_ids"]:
                if menu_id in menu_dict:
                    role.menus.append(menu_dict[menu_id])

            logger.info(f"Created role: {role.name}")

    await db.commit()
    logger.info("RBAC roles initialized")


async def init_roles_and_permissions(db: AsyncSession):
    """Initialize default roles and permissions"""
    await init_rbac_permissions(db)
    await init_legacy_permissions(db)
    await init_rbac_roles(db)
    logger.info("Roles and permissions initialized")


async def create_admin_user(
    db: AsyncSession,
    email: str = "admin@example.com",
    username: str = "admin",
    password: str = "admin123",
    full_name: str = "System Administrator",
):
    """Create default admin user if not exists"""
    result = await db.execute(select(User).where(User.username == username))
    admin = result.scalar_one_or_none()

    if admin:
        logger.info(f"Admin user already exists: {username}")
        return admin

    admin = User(
        email=email,
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    await db.flush()

    # Assign Admin role
    result = await db.execute(select(Role).where(Role.name == "Admin"))
    admin_role = result.scalar_one_or_none()
    if admin_role:
        admin.roles.append(admin_role)

    await db.commit()
    logger.info(f"Admin user created: {username} (password: {password})")
    return admin


async def init_default_departments(db: AsyncSession):
    """Initialize default departments"""
    logger.info("Initializing default departments...")

    # 检查是否已存在部门
    result = await db.execute(select(Department).where(Department.code == "default"))
    if result.scalar_one_or_none():
        logger.info("Default department already exists")
        return

    # 创建默认公司
    default_company = Department(
        name="默认公司",
        code="default",
        dept_type="company",
        level=1,
        tree_path="/",
        is_active=True,
        sort_order=0,
    )
    db.add(default_company)
    await db.commit()
    await db.refresh(default_company)

    # 更新 tree_path
    default_company.tree_path = f"/{default_company.id}/"
    await db.commit()

    logger.info(f"Created default company: {default_company.name}")

    # 创建示例部门
    tech_dept = Department(
        name="技术部",
        code="tech",
        parent_id=default_company.id,
        dept_type="department",
        level=2,
        tree_path=f"/{default_company.id}/",
        is_active=True,
        sort_order=1,
    )
    db.add(tech_dept)
    await db.commit()
    await db.refresh(tech_dept)

    tech_dept.tree_path = f"/{default_company.id}/{tech_dept.id}/"
    await db.commit()

    logger.info(f"Created department: {tech_dept.name}")
    logger.info("Default departments initialized")


async def init_default_menus(db: AsyncSession):
    """Initialize default menus"""
    logger.info("Initializing default menus...")

    # 检查是否已存在菜单
    result = await db.execute(select(Menu).where(Menu.path == "/admin"))
    if result.scalar_one_or_none():
        logger.info("Default menus already exist")
        return

    # 系统管理一级菜单
    admin_menu = Menu(
        name="系统管理",
        name_i18n="menu.admin",
        menu_type="menu",
        path="/admin",
        icon="Settings",
        order=100,
        is_visible=True,
        is_active=True,
        level=1,
        tree_path="/",
    )
    db.add(admin_menu)
    await db.commit()
    await db.refresh(admin_menu)

    admin_menu.tree_path = f"/{admin_menu.id}/"
    await db.commit()

    # 子菜单
    menus_data = [
        {
            "name": "用户管理",
            "name_i18n": "menu.users",
            "path": "/admin/users",
            "component": "admin/UserManagement",
            "icon": "Users",
            "order": 1,
            "permission": "user:read",
        },
        {
            "name": "角色管理",
            "name_i18n": "menu.roles",
            "path": "/admin/roles",
            "component": "admin/RoleManagement",
            "icon": "Shield",
            "order": 2,
            "permission": "role:read",
        },
        {
            "name": "部门管理",
            "name_i18n": "menu.departments",
            "path": "/admin/departments",
            "component": "admin/DepartmentManagement",
            "icon": "Building",
            "order": 3,
            "permission": "dept:read",
        },
        {
            "name": "菜单管理",
            "name_i18n": "menu.menus",
            "path": "/admin/menus",
            "component": "admin/MenuManagement",
            "icon": "Menu",
            "order": 4,
            "permission": "menu:read",
        },
    ]

    for menu_data in menus_data:
        menu = Menu(
            name=menu_data["name"],
            name_i18n=menu_data["name_i18n"],
            menu_type="sub_menu",
            path=menu_data["path"],
            component=menu_data["component"],
            icon=menu_data["icon"],
            parent_id=admin_menu.id,
            order=menu_data["order"],
            permission=menu_data["permission"],
            is_visible=True,
            is_active=True,
            level=2,
            tree_path=f"/{admin_menu.id}/",
        )
        db.add(menu)

    await db.commit()

    # 更新子菜单 tree_path
    result = await db.execute(
        select(Menu).where(Menu.parent_id == admin_menu.id)
    )
    sub_menus = result.scalars().all()
    for sub_menu in sub_menus:
        sub_menu.tree_path = f"/{admin_menu.id}/{sub_menu.id}/"
    await db.commit()

    logger.info(f"Created {len(menus_data) + 1} default menus")
    logger.info("Default menus initialized")


async def initialize_auth(db: AsyncSession):
    """Initialize authentication system"""
    await init_default_departments(db)
    await init_default_menus(db)
    await init_roles_and_permissions(db)
    await create_admin_user(db)
    logger.info("Authentication system initialized")
