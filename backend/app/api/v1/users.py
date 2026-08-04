"""
User Management API: Admin-only user and role management
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from app.models.user import User, Role, Permission, AuditLog
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    RoleAssignRequest,
    RoleResponse,
    RoleListResponse,
)
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    role: Optional[str] = None,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users (Admin only).
    Supports filtering by search term and role.
    """
    query = select(User)

    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )

    if role:
        query = query.join(User.roles).where(Role.name == role)

    query = query.options(selectinload(User.roles)).offset(skip).limit(limit).order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().unique().all()

    # Get total count
    count_query = select(User)
    if search:
        count_query = count_query.where(
            (User.email.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )
    if role:
        count_query = count_query.join(User.roles).where(Role.name == role)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


# ============== Role Management (must be before /{user_id} to avoid conflicts) ==============

@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    List all roles (Admin only).
    """
    result = await db.execute(select(Role).order_by(Role.name))
    roles = result.unique().scalars().all()

    return RoleListResponse(
        items=[RoleResponse.model_validate(r) for r in roles]
    )


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    request: Request,
    role_name: str,
    description: Optional[str] = None,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new role (Admin only).
    """
    # Check if role exists
    result = await db.execute(select(Role).where(Role.name == role_name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role already exists",
        )

    role = Role(
        name=role_name,
        description=description,
        is_system=False,
    )

    db.add(role)
    await db.commit()
    await db.refresh(role)

    # Log audit
    await _log_audit(
        request=request,
        current_user=current_user,
        action="role.create",
        resource_type="role",
        resource_id=role_name,
        status_code=201,
        db=db,
    )

    return RoleResponse.model_validate(role)


@router.delete("/roles/{role_id}")
async def delete_role(
    request: Request,
    role_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a role (Admin only). System roles cannot be deleted.
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system roles",
        )

    await db.delete(role)
    await db.commit()

    # Log audit
    await _log_audit(
        request=request,
        current_user=current_user,
        action="role.delete",
        resource_type="role",
        resource_id=str(role_id),
        status_code=200,
        db=db,
    )

    return {"message": f"Role '{role.name}' deleted successfully"}


# ============== User Management ==============


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user details by ID (Admin only).
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id)
    )
    user = result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # 构造用户响应，包含角色信息
    user_dict = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "tenant_id": user.tenant_id,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "roles": [{"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system} for r in user.roles],
    }
    return user_dict


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user (Admin only).
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(
            (User.email == user_data.email) | (User.username == user_data.username)
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already exists",
        )

    # Create user
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=hash_password(user_data.password),
        tenant_id=user_data.tenant_id,
        is_active=user_data.is_active,
    )

    # Assign roles if provided
    if user_data.role_ids:
        roles_result = await db.execute(
            select(Role).where(Role.id.in_(user_data.role_ids))
        )
        roles = roles_result.unique().scalars().all()
        user.roles = roles

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 显式加载角色
    if user_data.role_ids:
        await db.execute(select(Role).where(Role.id.in_(user_data.role_ids)))
        await db.refresh(user, attribute_names=['roles'])

    # 重新加载用户及其角色
    await db.refresh(user)
    result = await db.execute(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.roles))
    )
    user = result.unique().scalar_one()

    # Log audit
    await _log_audit(
        request=request,
        current_user=current_user,
        action="user.create",
        resource_type="user",
        resource_id=str(user.id),
        status_code=201,
        db=db,
    )

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user details (Admin only).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "password" and value:
            setattr(user, "hashed_password", hash_password(value))
        else:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    # Log audit
    await _log_audit(
        request=request,
        current_user=current_user,
        action="user.update",
        resource_type="user",
        resource_id=str(user_id),
        status_code=200,
        db=db,
    )

    return UserResponse.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a user (Admin only).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent deleting self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    await db.delete(user)
    await db.commit()

    # Log audit
    await _log_audit(
        request=request,
        current_user=current_user,
        action="user.delete",
        resource_type="user",
        resource_id=str(user_id),
        status_code=200,
        db=db,
    )

    return {"message": "User deleted successfully"}


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_user_roles(
    request: Request,
    user_id: int,
    role_data: RoleAssignRequest,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign roles to a user (Admin only).
    """
    from app.core.database import get_sync_db
    from sqlalchemy.orm import Session

    # 使用同步 session 避免 selectinload 污染
    sync_db: Session = next(get_sync_db())
    try:
        # Get user
        user = sync_db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Get roles
        roles = sync_db.query(Role).filter(Role.id.in_(role_data.role_ids)).all()
        if len(roles) != len(role_data.role_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more roles not found",
            )

        # 清除现有角色并分配新角色
        user.roles = roles
        sync_db.commit()

        # 返回用户信息
        sync_db.refresh(user)
        result = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "roles": [{"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system} for r in roles],
            "created_at": user.created_at,
        }
        return result
    finally:
        sync_db.close()


@router.get("/{user_id}/roles", response_model=List[RoleResponse])
async def get_user_roles(
    user_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get roles assigned to a user (Admin only).
    """
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return [RoleResponse.model_validate(r) for r in user.roles]


async def _log_audit(
    request: Request,
    current_user: User,
    action: str,
    resource_type: str,
    resource_id: str,
    status_code: int,
    db: AsyncSession,
    details: Optional[str] = None,
):
    """Helper to log audit events"""
    from app.core.auth import log_audit
    await log_audit(
        request=request,
        current_user=current_user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status_code=status_code,
        db=db,
        details=details,
    )
