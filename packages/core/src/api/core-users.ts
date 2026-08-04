/**
 * Core API - User & Role Management
 * 用户与角色管理 API
 */
import { fetchApi } from '@packages/core/api/core';

// ============================================================
// User Management types and functions
// ============================================================

export interface RoleData {
  id: number;
  name: string;
  description?: string;
  isSystem?: boolean;
}

export interface UserData {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active?: boolean;
  created_at?: string;
  roles?: RoleData[];
}

export interface UserCreate {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  role_ids?: number[];
}

export const fetchUsers = async (search?: string, role?: string) => {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (role) params.set('role', role);
  const qs = params.toString();
  return fetchApi(`/api/v1/users${qs ? `?${qs}` : ''}`);
};

export const fetchRoles = async () => {
  return fetchApi('/api/v1/users/roles');
};

export const createUser = async (data: UserCreate) => {
  return fetchApi('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateUser = async (id: number, data: Partial<UserData>) => {
  return fetchApi(`/api/v1/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteUser = async (id: number) => {
  return fetchApi(`/api/v1/users/${id}`, { method: 'DELETE' });
};

export const assignUserRoles = async (id: number, roleIds: number[]) => {
  return fetchApi(`/api/v1/users/${id}/roles`, {
    method: 'POST',
    body: JSON.stringify({ role_ids: roleIds }),
  });
};

export const createRole = async (name: string, description?: string) => {
  const qs = description ? `?description=${encodeURIComponent(description)}` : '';
  return fetchApi(`/api/v1/users/roles?role_name=${encodeURIComponent(name)}${qs}`, {
    method: 'POST',
  });
};

export const updateRole = async (id: number, data: { name?: string; description?: string }) => {
  return fetchApi(`/api/v1/users/roles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteRole = async (id: number) => {
  return fetchApi(`/api/v1/users/roles/${id}`, { method: 'DELETE' });
};
