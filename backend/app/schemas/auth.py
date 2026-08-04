"""
Authentication schemas: login, register, tokens, API keys
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# =============================================================================
# Login / Register
# =============================================================================


class LoginRequest(BaseModel):
    """Login request with username/email and password"""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class UserCreate(BaseModel):
    """User registration request"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    tenant_id: Optional[str] = None


class UserResponse(BaseModel):
    """User profile response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    tenant_id: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None
    roles: List["RoleResponse"] = []


# Import RoleResponse to avoid circular import - must be at end
from app.schemas.user import RoleResponse


# =============================================================================
# API Keys
# =============================================================================


class APIKeyCreate(BaseModel):
    """API key creation request"""
    name: str = Field(..., min_length=1, max_length=100, description="Friendly name for the key")
    rate_limit: Optional[int] = Field(None, ge=1, description="Requests per minute")
    daily_quota: Optional[int] = Field(None, ge=1, description="Daily request quota")
    expires_at: Optional[datetime] = Field(None, description="Key expiration time")


class APIKeyResponse(BaseModel):
    """API key response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str  # First 8 chars for identification
    full_key: Optional[str] = None  # Only shown once on creation
    is_active: bool
    rate_limit: Optional[int] = None
    daily_quota: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class APIKeyListResponse(BaseModel):
    """API key list response"""
    items: List[APIKeyResponse]


# =============================================================================
# Audit Logs
# =============================================================================


class AuditLogResponse(BaseModel):
    """Audit log entry response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    request_method: Optional[str]
    request_path: Optional[str]
    ip_address: Optional[str]
    status_code: Optional[int]
    created_at: datetime
