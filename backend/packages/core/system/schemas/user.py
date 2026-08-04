"""
User and Role management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# =============================================================================
# User Schemas
# =============================================================================


class UserCreate(BaseModel):
    """User creation request (Admin)"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    tenant_id: Optional[str] = None
    is_active: bool = True
    role_ids: Optional[List[int]] = None  # Role IDs to assign


class UserUpdate(BaseModel):
    """User update request (Admin)"""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[str] = None


class UserResponse(BaseModel):
    """User profile response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    tenant_id: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None
    roles: List["RoleResponse"] = []  # Assigned roles


class UserListResponse(BaseModel):
    """User list response with pagination"""
    items: List[UserResponse]
    total: int
    skip: int
    limit: int


# =============================================================================
# Role Schemas
# =============================================================================


class RoleResponse(BaseModel):
    """Role response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    is_system: bool  # System roles cannot be deleted


class RoleListResponse(BaseModel):
    """Role list response"""
    items: List[RoleResponse]


class RoleAssignRequest(BaseModel):
    """Role assignment request"""
    role_ids: List[int] = Field(..., min_length=1)


class RoleCreate(BaseModel):
    """Role creation request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    """Role update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


# =============================================================================
# Permission Schemas
# =============================================================================


class PermissionResponse(BaseModel):
    """Permission response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    resource: str  # e.g., 'document', 'knowledge_base'
    action: str  # e.g., 'create', 'read', 'update', 'delete'


class PermissionCreate(BaseModel):
    """Permission creation request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    resource: str
    action: str


class RolePermissionAssignRequest(BaseModel):
    """Assign permissions to role request"""
    permission_ids: List[int] = Field(..., min_length=1)


class RoleMenuAssignRequest(BaseModel):
    """Assign menus to role request"""
    menu_ids: List[int] = Field(..., min_length=1)


class RoleCreate(BaseModel):
    """Role creation request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    tenant_id: Optional[str] = None


class RoleUpdate(BaseModel):
    """Role update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    menu_ids: Optional[List[int]] = None
    permission_ids: Optional[List[int]] = None


class RoleDetailResponse(RoleResponse):
    """Role detail response with permissions and menus"""
    permissions: List[PermissionResponse] = []
    menus: List["MenuResponse"] = []


# Import MenuResponse to avoid circular import
from packages.core.system.schemas.menu import MenuResponse
