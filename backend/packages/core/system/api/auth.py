"""
Authentication API: login, register, token management, API keys
"""
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import hashlib

from packages.core.database import get_db, get_sync_db
from sqlalchemy.orm import Session
from packages.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
    hash_password,
    verify_password,
)
from packages.core.auth import (
    get_current_user,
    get_current_user_or_api_key,
    generate_api_key,
    hash_api_key,
    log_audit,
)
from packages.core.system.models.user import User, APIKey, Role, AuditLog
from packages.core.system.models.department import UserDepartment
from packages.core.system.models.menu import Menu
from packages.core.system.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserCreate,
    UserResponse,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyListResponse,
)
from packages.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and return JWT tokens.
    """
    # Find user by email or username with roles preloaded
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(
            (User.email == login_data.username) | (User.username == login_data.username)
        )
    )
    user = result.unique().scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # Create tokens
    access_token = create_access_token(
        subject=user.id,
        secret_key=settings.secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = create_refresh_token(
        subject=user.id,
        secret_key=settings.secret_key,
    )

    # Log audit
    await log_audit(
        request=request,
        current_user=user,
        action="auth.login",
        status_code=200,
        db=db,
    )

    # 重新查询用户以获取角色（避免 lazy loading）
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user.id)
    )
    user_with_roles = result.unique().scalar_one()

    # 构造用户响应，包含角色信息
    user_dict = {
        "id": user_with_roles.id,
        "email": user_with_roles.email,
        "username": user_with_roles.username,
        "full_name": user_with_roles.full_name,
        "is_active": user_with_roles.is_active,
        "is_superuser": user_with_roles.is_superuser,
        "tenant_id": user_with_roles.tenant_id,
        "created_at": user_with_roles.created_at,
        "last_login_at": user_with_roles.last_login_at,
        "roles": [{"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system} for r in user_with_roles.roles],
    }

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user_dict,
    )


@router.post("/register", response_model=UserResponse)
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user.
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
            detail="Email or username already registered",
        )

    # Create user
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=hash_password(user_data.password),
        tenant_id=user_data.tenant_id,
        is_active=True,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Log audit
    await log_audit(
        request=request,
        current_user=user,
        action="auth.register",
        status_code=201,
        db=db,
    )

    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token.
    """
    payload = verify_token(request.refresh_token, settings.secret_key)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    access_token = create_access_token(
        subject=user.id,
        secret_key=settings.secret_key,
    )
    refresh_token = create_refresh_token(
        subject=user.id,
        secret_key=settings.secret_key,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get current user profile.
    """
    return UserResponse.model_validate(current_user)


@router.get("/me/menus")
async def get_current_user_menus(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    """
    获取当前用户有权限的菜单树
    """
    from packages.core.system.services.menu_service import MenuService

    service = MenuService(db)

    # 超级管理员返回所有菜单（检查 is_superuser 字段或 super_admin 角色）
    if current_user.is_superuser or current_user.has_role('super_admin'):
        tree = service.get_menu_tree()
        return {"items": tree, "total": len(tree)}

    # 普通用户返回有权限的菜单
    tree = service.get_user_menu_tree(current_user.id)
    return {"items": tree, "total": len(tree)}


@router.get("/me/permissions")
async def get_current_user_permissions(
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的所有权限
    """
    permissions = set()
    for role in current_user.roles:
        for perm in role.permissions:
            permissions.add(perm.name)

    return {
        "permissions": list(permissions),
        "roles": [role.name for role in current_user.roles],
    }


@router.get("/me/departments")
async def get_current_user_departments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户所属的部门
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(UserDepartment)
        .where(UserDepartment.user_id == current_user.id)
        .options(selectinload(UserDepartment.department))
        .order_by(UserDepartment.is_primary.desc())
    )
    user_depts = result.scalars().all()

    return {
        "items": [
            {
                "id": ud.id,
                "department_id": ud.department_id,
                "department_name": ud.department.name,
                "dept_role": ud.dept_role,
                "is_primary": ud.is_primary,
                "joined_at": ud.joined_at,
            }
            for ud in user_depts
        ],
        "primary_department": user_depts[0].department if user_depts and user_depts[0].is_primary else None,
    }


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: Request,
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key for the current user.
    The full key is shown only once - store it securely!
    """
    full_key, prefix = generate_api_key()
    key_hash = hash_api_key(full_key)

    api_key = APIKey(
        user_id=current_user.id,
        key_hash=key_hash,
        name=key_data.name,
        prefix=prefix,
        rate_limit=key_data.rate_limit,
        daily_quota=key_data.daily_quota,
        expires_at=key_data.expires_at,
    )

    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    # Log audit
    await log_audit(
        request=request,
        current_user=current_user,
        action="api_key.create",
        resource_type="api_key",
        resource_id=str(api_key.id),
        status_code=201,
        db=db,
    )

    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        full_key=full_key,  # Only shown once!
        is_active=api_key.is_active,
        rate_limit=api_key.rate_limit,
        daily_quota=api_key.daily_quota,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all API keys for the current user.
    Full keys are not returned - only prefixes for identification.
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()

    return APIKeyListResponse(
        items=[
            APIKeyResponse(
                id=key.id,
                name=key.name,
                prefix=key.prefix,
                full_key=None,  # Never return full key
                is_active=key.is_active,
                rate_limit=key.rate_limit,
                daily_quota=key.daily_quota,
                created_at=key.created_at,
                expires_at=key.expires_at,
                last_used_at=key.last_used_at,
            )
            for key in keys
        ]
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    request: Request,
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke (delete) an API key.
    """
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    await db.delete(api_key)
    await db.commit()

    # Log audit
    await log_audit(
        request=request,
        current_user=current_user,
        action="api_key.revoke",
        resource_type="api_key",
        resource_id=str(key_id),
        status_code=200,
        db=db,
    )

    return {"message": "API key revoked successfully"}


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List audit logs for the current user.
    """
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()

    return logs
