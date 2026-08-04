/**
 * Core API - Admin (Department & Menu Management)
 * 部门与菜单管理 API
 */
import { fetchApi } from '@packages/core/api/core';
import type { MenuData, MenuTreeResponse } from '@packages/core/api/core-auth';

// ============================================================
// Department Management
// ============================================================

export interface DepartmentData {
  id: number;
  name: string;
  code: string;
  description?: string;
  parent_id?: number;
  level: number;
  tree_path?: string;
  dept_type?: string;
  sort_order?: number;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  children?: DepartmentData[];
}

export interface DepartmentListResponse {
  items: DepartmentData[];
  total: number;
}

export interface DepartmentTreeResponse {
  items: DepartmentData[];
  total: number;
}

export const fetchDepartments = async () => {
  return fetchApi<DepartmentListResponse>('/api/v1/admin/departments');
};

export const fetchDepartmentTree = async () => {
  return fetchApi<DepartmentTreeResponse>('/api/v1/admin/departments/tree');
};

export const createDepartment = async (data: { name: string; description?: string; parent_id?: number }) => {
  return fetchApi('/api/v1/admin/departments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateDepartment = async (deptId: number, data: { name?: string; description?: string; parent_id?: number }) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteDepartment = async (deptId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}`, { method: 'DELETE' });
};

export const getDepartmentUsers = async (deptId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users`);
};

export const addUserToDepartment = async (deptId: number, userId: number, dept_role?: string, is_primary?: boolean) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, dept_role, is_primary }),
  });
};

export const removeUserFromDepartment = async (deptId: number, userId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users/${userId}`, { method: 'DELETE' });
};

// ============================================================
// Menu Management
// ============================================================

export interface MenuListResponse {
  items: MenuData[];
  total: number;
}

export const fetchMenus = async () => {
  return fetchApi<MenuListResponse>('/api/v1/admin/menus');
};

export const fetchMenuTree = async () => {
  return fetchApi<MenuTreeResponse>('/api/v1/admin/menus/tree');
};

export const createMenu = async (data: {
  name: string;
  name_i18n?: string;
  menu_type: string;
  path: string;
  component?: string;
  icon?: string;
  order?: number;
  parent_id?: number;
  permission?: string;
  is_visible?: boolean;
  is_active?: boolean;
}) => {
  return fetchApi('/api/v1/admin/menus', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateMenu = async (menuId: number, data: {
  name?: string;
  name_i18n?: string;
  path?: string;
  component?: string;
  icon?: string;
  order?: number;
  permission?: string;
  is_visible?: boolean;
  is_active?: boolean;
}) => {
  return fetchApi(`/api/v1/admin/menus/${menuId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteMenu = async (menuId: number) => {
  return fetchApi(`/api/v1/admin/menus/${menuId}`, { method: 'DELETE' });
};

export const assignMenusToRole = async (roleId: number, menuIds: number[]) => {
  return fetchApi(`/api/v1/admin/roles/${roleId}/menus`, {
    method: 'PUT',
    body: JSON.stringify({ menu_ids: menuIds }),
  });
};
