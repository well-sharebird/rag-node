"""
Menu management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Menu Schemas
# =============================================================================


class MenuBase(BaseModel):
    """Menu base schema"""
    name: str = Field(..., min_length=1, max_length=100)
    name_i18n: Optional[str] = None
    menu_type: str = "menu"  # menu, sub_menu, button
    path: str = Field(..., max_length=255)
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    order: int = 0
    parent_id: Optional[int] = None
    permission: Optional[str] = None
    is_visible: bool = True
    is_hidden: bool = False
    is_external: bool = False
    external_url: Optional[str] = None
    keep_alive: bool = True
    is_active: bool = True


class MenuCreate(MenuBase):
    """Menu creation request"""
    pass


class MenuUpdate(BaseModel):
    """Menu update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    name_i18n: Optional[str] = None
    menu_type: Optional[str] = None
    path: Optional[str] = Field(None, max_length=255)
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None
    parent_id: Optional[int] = None
    permission: Optional[str] = None
    is_visible: Optional[bool] = None
    is_hidden: Optional[bool] = None
    is_external: Optional[bool] = None
    external_url: Optional[str] = None
    keep_alive: Optional[bool] = None
    is_active: Optional[bool] = None


class MenuResponse(BaseModel):
    """Menu response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_i18n: Optional[str] = None
    menu_type: str
    path: str
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    order: int
    parent_id: Optional[int] = None
    level: int
    tree_path: str
    permission: Optional[str] = None
    is_visible: bool
    is_hidden: bool
    is_external: bool
    external_url: Optional[str] = None
    keep_alive: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    children: List["MenuResponse"] = []


class MenuTreeResponse(BaseModel):
    """Menu tree response"""
    items: List[MenuResponse]
    total: int


class MenuListResponse(BaseModel):
    """Menu list response"""
    items: List[MenuResponse]
    total: int


# =============================================================================
# Menu Sync Schemas
# =============================================================================


class MenuSyncItem(BaseModel):
    """Menu sync item for bulk synchronization"""
    path: str
    name: str
    name_i18n: Optional[str] = None
    menu_type: str = "menu"
    component: Optional[str] = None
    icon: Optional[str] = None
    order: int = 0
    permission: Optional[str] = None
    is_visible: bool = True
    is_hidden: bool = False


class MenuSyncRequest(BaseModel):
    """Menu sync request - sync frontend routes to backend"""
    menus: List[MenuSyncItem]


class MenuSyncResult(BaseModel):
    """Menu sync result"""
    created: int
    updated: int
    deleted: int
    menus: List[MenuResponse] = []
