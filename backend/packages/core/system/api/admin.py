"""
Admin Management APIs - 后台管理接口
包含部门管理、菜单管理、角色管理
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload, Session, scoped_session
from sqlalchemy.orm import query as orm_query

from packages.core.database import get_db, get_sync_db
from packages.core.auth import get_current_user, require_role
from packages.core.system.models.user import User, Role, Permission
from packages.core.system.models.department import Department, UserDepartment
from packages.core.system.models.menu import Menu
from packages.core.system.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentTreeResponse,
    DepartmentListResponse,
    UserDepartmentResponse,
    UserDepartmentCreate,
    UserDepartmentUpdate,
)
from packages.core.system.schemas.menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuTreeResponse,
    MenuListResponse,
    MenuSyncRequest,
    MenuSyncResult,
)
from packages.core.system.schemas.user import (
    RoleResponse,
    RoleListResponse,
    RoleCreate,
    RoleUpdate,
    RoleDetailResponse,
    RoleMenuAssignRequest,
    RolePermissionAssignRequest,
    PermissionResponse,
)
from packages.core.system.services.department_service import DepartmentService
from packages.core.system.services.menu_service import MenuService

# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(prefix="/admin", tags=["Admin Management"])


# =============================================================================
# Department Management APIs
# =============================================================================

dept_router = APIRouter(prefix="/departments", tags=["Department Management"])


@dept_router.get("", response_model=DepartmentListResponse)
async def list_departments(
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取部门列表（树形结构）
    """
    service = DepartmentService(db)
    depts = service.get_all_depts()
    tree = []
    for dept in depts:
        if dept.parent_id is None:
            tree.append(service._dept_to_dict(dept))

    return DepartmentListResponse(items=depts, total=len(depts))


@dept_router.get("/tree", response_model=DepartmentTreeResponse)
async def get_department_tree(
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取部门树形结构
    """
    service = DepartmentService(db)
    tree = service.get_dept_tree()
    return DepartmentTreeResponse(items=tree, total=len(tree))


@dept_router.get("/{dept_id}", response_model=DepartmentResponse)
async def get_department(
    dept_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取部门详情
    """
    service = DepartmentService(db)
    dept = service.get_department(dept_id)

    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")

    return DepartmentResponse.model_validate(dept)


@dept_router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    request: Request,
    data: DepartmentCreate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    创建部门
    """
    service = DepartmentService(db)

    try:
        dept = service.create_department(data)
        return DepartmentResponse.model_validate(dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dept_router.put("/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    request: Request,
    dept_id: int,
    data: DepartmentUpdate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    更新部门
    """
    service = DepartmentService(db)

    try:
        dept = service.update_department(dept_id, data)
        if not dept:
            raise HTTPException(status_code=404, detail="部门不存在")
        return DepartmentResponse.model_validate(dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dept_router.delete("/{dept_id}")
async def delete_department(
    request: Request,
    dept_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    删除部门
    """
    service = DepartmentService(db)

    try:
        success = service.delete_department(dept_id)
        if not success:
            raise HTTPException(status_code=404, detail="部门不存在")
        return {"message": "部门已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dept_router.get("/{dept_id}/users", response_model=List[UserDepartmentResponse])
async def get_department_users(
    dept_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取部门下的用户列表
    """
    # 获取用户在当前部门的关联信息
    result = db.execute(
        select(UserDepartment)
        .where(UserDepartment.department_id == dept_id)
        .options(selectinload(UserDepartment.department))
    )
    user_depts = result.scalars().all()

    return [UserDepartmentResponse.model_validate(ud) for ud in user_depts]


@dept_router.post("/{dept_id}/users", response_model=UserDepartmentResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_department(
    request: Request,
    dept_id: int,
    data: UserDepartmentCreate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    添加用户到部门
    """
    service = DepartmentService(db)

    try:
        user_dept = service.add_user_to_dept(
            dept_id=dept_id,
            user_id=data.user_id,
            role=data.dept_role,
            is_primary=data.is_primary
        )
        return UserDepartmentResponse.model_validate(user_dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dept_router.delete("/{dept_id}/users/{user_id}")
async def remove_user_from_department(
    request: Request,
    dept_id: int,
    user_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    从部门移除用户
    """
    service = DepartmentService(db)

    success = service.remove_user_from_dept(dept_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不在该部门中")

    return {"message": "用户已从部门移除"}


# =============================================================================
# Menu Management APIs
# =============================================================================

menu_router = APIRouter(prefix="/menus", tags=["Menu Management"])


@menu_router.get("", response_model=MenuListResponse)
async def list_menus(
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取菜单列表（树形结构）
    """
    service = MenuService(db)
    tree = service.get_menu_tree()
    return MenuListResponse(items=tree, total=len(tree))


@menu_router.get("/tree", response_model=MenuTreeResponse)
async def get_menu_tree(
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取菜单树形结构
    """
    service = MenuService(db)
    tree = service.get_menu_tree()
    return MenuTreeResponse(items=tree, total=len(tree))


@menu_router.get("/{menu_id}", response_model=MenuResponse)
async def get_menu(
    menu_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取菜单详情
    """
    service = MenuService(db)
    menu = service.get_menu(menu_id)

    if not menu:
        raise HTTPException(status_code=404, detail="菜单不存在")

    return MenuResponse.model_validate(menu)


@menu_router.post("", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
async def create_menu(
    request: Request,
    data: MenuCreate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    创建菜单
    """
    service = MenuService(db)
    menu = service.create_menu(data)
    return MenuResponse.model_validate(menu)


@menu_router.put("/{menu_id}", response_model=MenuResponse)
async def update_menu(
    request: Request,
    menu_id: int,
    data: MenuUpdate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    更新菜单
    """
    service = MenuService(db)

    menu = service.update_menu(menu_id, data)
    if not menu:
        raise HTTPException(status_code=404, detail="菜单不存在")

    return MenuResponse.model_validate(menu)


@menu_router.delete("/{menu_id}")
async def delete_menu(
    request: Request,
    menu_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    删除菜单
    """
    service = MenuService(db)

    try:
        success = service.delete_menu(menu_id)
        if not success:
            raise HTTPException(status_code=404, detail="菜单不存在")
        return {"message": "菜单已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@menu_router.post("/sync", response_model=MenuSyncResult)
async def sync_menus(
    request: Request,
    data: MenuSyncRequest,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    同步菜单（用于前端路由同步）
    """
    service = MenuService(db)
    result = service.sync_menus(data.menus)

    # 获取同步后的菜单列表
    menus = service.get_all_menus()

    return MenuSyncResult(
        created=result["created"],
        updated=result["updated"],
        deleted=result["deleted"],
        menus=menus,
    )


# =============================================================================
# Role Management APIs
# =============================================================================

role_router = APIRouter(prefix="/roles", tags=["Role Management"])


@role_router.get("", response_model=RoleListResponse)
async def list_roles(
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取角色列表
    """
    result = db.execute(
        select(Role)
        .options(selectinload(Role.permissions), selectinload(Role.menus))
        .order_by(Role.name)
    ).unique()
    roles = result.scalars().all()
    return RoleListResponse(items=[RoleDetailResponse.model_validate(r) for r in roles])


@role_router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    获取角色详情
    """
    result = db.execute(
        select(Role)
        .where(Role.id == role_id)
        .options(selectinload(Role.permissions), selectinload(Role.menus))
    ).unique()
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    return RoleDetailResponse.model_validate(role)


@role_router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    request: Request,
    data: RoleCreate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    创建角色
    """
    # 检查角色是否已存在
    result = db.execute(select(Role).where(Role.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="角色已存在")

    role = Role(**data.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)

    return RoleResponse.model_validate(role)


@role_router.put("/{role_id}", response_model=RoleDetailResponse)
async def update_role(
    request: Request,
    role_id: int,
    data: RoleUpdate,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    更新角色
    """
    result = db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.is_system:
        raise HTTPException(status_code=400, detail="系统角色不可修改")

    update_data = data.model_dump(exclude_unset=True)

    # 处理菜单分配
    menu_ids = update_data.pop("menu_ids", None)
    if menu_ids is not None:
        menu_service = MenuService(db)
        menu_service.assign_menus_to_role(role_id, menu_ids)

    # 处理权限分配
    permission_ids = update_data.pop("permission_ids", None)
    if permission_ids is not None:
        perm_result = db.execute(
            select(Permission).where(Permission.id.in_(permission_ids))
        )
        role.permissions = perm_result.scalars().all()

    # 更新其他字段
    for field, value in update_data.items():
        setattr(role, field, value)

    db.commit()
    db.refresh(role)

    return RoleDetailResponse.model_validate(role)


@role_router.delete("/{role_id}")
async def delete_role(
    request: Request,
    role_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    删除角色
    """
    result = db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.is_system:
        raise HTTPException(status_code=400, detail="系统角色不可删除")

    db.delete(role)
    db.commit()

    return {"message": f"角色 '{role.name}' 已删除"}


@role_router.put("/{role_id}/menus", response_model=RoleDetailResponse)
async def assign_role_menus(
    request: Request,
    role_id: int,
    data: RoleMenuAssignRequest,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    为角色分配菜单
    """
    # 检查角色是否存在（不使用 selectinload 避免 unique 问题）
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    menu_service = MenuService(db)
    menu_service.assign_menus_to_role(role_id, data.menu_ids)

    # 重新加载角色（使用 query 避免 unique 问题）
    role_with_menus = db.query(Role).options(
        selectinload(Role.permissions),
        selectinload(Role.menus)
    ).filter(Role.id == role_id).one_or_none()

    return RoleDetailResponse.model_validate(role_with_menus)


@role_router.put("/{role_id}/permissions", response_model=RoleDetailResponse)
async def assign_role_permissions(
    request: Request,
    role_id: int,
    data: RolePermissionAssignRequest,
    current_user: User = Depends(require_role("Admin")),
    db: Session = Depends(get_sync_db),
):
    """
    为角色分配权限
    """
    result = db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    # 获取权限
    perm_result = db.execute(
        select(Permission).where(Permission.id.in_(data.permission_ids))
    )
    permissions = perm_result.scalars().all()

    role.permissions = permissions
    db.commit()
    db.refresh(role)

    return RoleDetailResponse.model_validate(role)


# =============================================================================
# Register Routers
# =============================================================================

# 注册子路由
router.include_router(dept_router)
router.include_router(menu_router)
router.include_router(role_router)
