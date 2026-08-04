"""
Authentication dependencies and middleware
"""
from datetime import datetime
from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
import hashlib
import secrets

from app.core.database import get_db
from app.core.security import verify_token, hash_password
from app.models.user import User, APIKey, AuditLog
from app.config import settings


# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

# Optional HTTP Bearer for endpoints that work with or without auth
security_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current authenticated user from JWT token.
    Raises HTTPException if authentication fails.
    """
    from sqlalchemy.orm import selectinload

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    payload = verify_token(token, settings.secret_key)

    if payload is None:
        raise credentials_exception

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    exp = datetime.fromtimestamp(payload.get("exp", 0))
    if exp < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database with roles preloaded
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == int(user_id))
    )
    user = result.unique().scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current admin user from JWT token.
    Requires user to have admin/superuser role.
    """
    user = await get_current_user(credentials, db)

    # Check if user is admin or superuser
    if user.is_superuser or user.has_role("admin") or user.has_role("Admin"):
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


async def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.
    Does not raise exceptions for unauthenticated requests.
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        payload = verify_token(token, settings.secret_key)

        if payload is None or payload.get("type") != "access":
            return None

        user_id = payload.get("sub")
        if user_id is None:
            return None

        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            return None

        return user
    except (JWTError, ValueError):
        return None


async def get_api_key(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[APIKey]:
    """
    Get API key from request header.
    Supports 'X-API-Key' header.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None

    # Hash the API key for comparison
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .where(APIKey.is_active == True)
    )
    api_key_obj = result.scalar_one_or_none()

    if api_key_obj:
        # Update usage tracking
        api_key_obj.last_used_at = datetime.utcnow()
        api_key_obj.used_today += 1
        await db.commit()

    return api_key_obj


async def get_current_user_or_api_key(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | APIKey:
    """
    Get current user via JWT token or API key.
    Raises HTTPException if neither is valid.
    """
    # Try JWT token first
    if credentials:
        try:
            user = await get_current_user(credentials, db)
            return user
        except HTTPException:
            pass

    # Try API key
    api_key = await get_api_key(request, db)
    if api_key:
        return api_key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(role_name: str):
    """
    Dependency factory that requires a specific role.
    Usage: Depends(require_role("Admin"))
    Supports multiple role names (case-insensitive) for compatibility.
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # Superusers always have access
        if current_user.is_superuser:
            return current_user

        # Check if user has super_admin role (equivalent to superuser)
        if current_user.has_role("super_admin"):
            return current_user

        # Check if user has the required role (case-insensitive)
        if current_user.has_role(role_name):
            return current_user

        # Check for equivalent roles (case variations)
        role_mappings = {
            "Admin": ["admin", "Admin"],
            "admin": ["Admin", "admin"],
            "Editor": ["editor", "Editor"],
            "editor": ["Editor", "editor"],
            "Viewer": ["viewer", "Viewer"],
            "viewer": ["Viewer", "viewer"],
        }

        equivalent_roles = role_mappings.get(role_name, [role_name])
        for role in current_user.roles:
            if role.name in equivalent_roles:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required role: {role_name}",
        )
    return role_checker


def require_permission(permission: str):
    """
    Dependency factory that requires a specific permission.
    Usage: Depends(require_permission("document.create"))
    """
    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return current_user
    return permission_checker


async def log_audit(
    request: Request,
    current_user: Optional[User],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    status_code: Optional[int] = None,
    db: Optional[AsyncSession] = None,
):
    """Log an audit entry"""
    if db is None:
        return

    audit_entry = AuditLog(
        user_id=current_user.id if current_user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_method=request.method,
        request_path=str(request.url.path),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status_code=status_code,
        details=details,
    )

    db.add(audit_entry)
    await db.commit()


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.
    Returns (full_key, prefix) tuple.
    The full_key should be shown to user once, prefix for identification.
    """
    full_key = f"sk_{secrets.token_urlsafe(32)}"
    prefix = full_key[:8]
    return full_key, prefix


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()
