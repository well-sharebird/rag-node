"""
Initialize default roles, permissions, and admin user
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, Role, Permission
from app.core.security import hash_password

logger = logging.getLogger(__name__)


DEFAULT_PERMISSIONS = [
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

DEFAULT_ROLES = [
    {
        "name": "admin",
        "description": "Full access to all resources",
        "is_system": True,
        "permissions": [p for p in DEFAULT_PERMISSIONS],
    },
    {
        "name": "editor",
        "description": "Can create and edit documents and knowledge bases",
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
        "name": "viewer",
        "description": "Read-only access",
        "is_system": True,
        "permissions": [
            ("knowledge_base", "read"),
            ("document", "read"),
            ("retrieval", "search"),
            ("retrieval", "chat"),
            ("settings", "read"),
        ],
    },
]


async def init_roles_and_permissions(db: AsyncSession):
    """Initialize default roles and permissions"""
    logger.info("Initializing roles and permissions...")

    # Create permissions
    for resource, action in DEFAULT_PERMISSIONS:
        result = await db.execute(
            select(Permission).where(
                Permission.name == f"{resource}.{action}"
            )
        )
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

    # Create roles
    for role_data in DEFAULT_ROLES:
        result = await db.execute(
            select(Role).where(Role.name == role_data["name"])
        )
        role = result.scalar_one_or_none()

        if not role:
            role = Role(
                name=role_data["name"],
                description=role_data["description"],
                is_system=role_data["is_system"],
            )
            db.add(role)
            await db.flush()

            # Assign permissions
            for perm_name, perm_action in role_data["permissions"]:
                result = await db.execute(
                    select(Permission).where(
                        Permission.name == f"{perm_name}.{perm_action}"
                    )
                )
                perm = result.scalar_one_or_none()
                if perm:
                    role.permissions.append(perm)

            logger.info(f"Created role: {role.name}")

    await db.commit()
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

    # Assign admin role
    result = await db.execute(select(Role).where(Role.name == "admin"))
    admin_role = result.scalar_one_or_none()
    if admin_role:
        admin.roles.append(admin_role)

    await db.commit()
    logger.info(f"Admin user created: {username} (password: {password})")
    return admin


async def initialize_auth(db: AsyncSession):
    """Initialize authentication system"""
    await init_roles_and_permissions(db)
    await create_admin_user(db)
