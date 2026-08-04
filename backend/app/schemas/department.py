"""
Department management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Department Schemas
# =============================================================================


class DepartmentBase(BaseModel):
    """Department base schema"""
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    parent_id: Optional[int] = None
    dept_type: str = "department"  # company, department, team, project_group
    leader_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    """Department creation request"""
    pass


class DepartmentUpdate(BaseModel):
    """Department update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    parent_id: Optional[int] = None
    dept_type: Optional[str] = None
    leader_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    description: Optional[str] = None


class DepartmentResponse(BaseModel):
    """Department response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    parent_id: Optional[int] = None
    level: int
    tree_path: str
    dept_type: str
    leader_id: Optional[int] = None
    leader_name: Optional[str] = None
    is_active: bool
    sort_order: int
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    children: List["DepartmentResponse"] = []


class DepartmentTreeResponse(BaseModel):
    """Department tree response"""
    items: List[DepartmentResponse]
    total: int


class DepartmentListResponse(BaseModel):
    """Department list response"""
    items: List[DepartmentResponse]
    total: int


# =============================================================================
# UserDepartment Schemas
# =============================================================================


class UserDepartmentBase(BaseModel):
    """UserDepartment base schema"""
    user_id: int
    department_id: int
    dept_role: str = "member"  # owner, admin, member, viewer
    is_primary: bool = False


class UserDepartmentCreate(UserDepartmentBase):
    """UserDepartment creation request"""
    pass


class UserDepartmentUpdate(BaseModel):
    """UserDepartment update request"""
    dept_role: Optional[str] = None
    is_primary: Optional[bool] = None


class UserDepartmentResponse(BaseModel):
    """UserDepartment response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    department_id: int
    dept_role: str
    is_primary: bool
    joined_at: datetime
    department: Optional[DepartmentResponse] = None


class UserDepartmentListResponse(BaseModel):
    """UserDepartment list response"""
    items: List[UserDepartmentResponse]
    total: int
